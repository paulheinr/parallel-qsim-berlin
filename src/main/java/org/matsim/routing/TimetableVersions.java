package org.matsim.routing;

import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptorData;
import ch.sbb.matsim.routing.pt.raptor.VersionedRaptorTimetable;
import ch.sbb.matsim.routing.pt.raptor.VersionedRaptorTimetable.TripUpdate;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Id;
import org.matsim.pt.transitSchedule.api.Departure;
import org.matsim.pt.transitSchedule.api.TransitLine;
import org.matsim.pt.transitSchedule.api.TransitRoute;
import org.matsim.pt.transitSchedule.api.TransitStopFacility;
import org.matsim.schemas.services.routing.v1.BaseDeparture;
import org.matsim.schemas.services.routing.v1.BaseRoute;
import org.matsim.schemas.services.routing.v1.TimetableDelta;

import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.function.IntToLongFunction;

import static org.matsim.routing.RoutingUtils.wholeSeconds;

/**
 * The timetable versions of one router, built one after another from the messages of the timetable stream (see
 * {@code TimetableService} in {@code matsim/services/routing/v1/routing.proto} of matsim-schemas) and filed under
 * (iteration, snapshot id).
 * <p>
 * The stream sends snapshot 0 route by route, then per iteration an iteration start and one delta per snapshot. A
 * message that breaks this contract makes the stream methods throw an {@link IllegalArgumentException} or an
 * {@link IllegalStateException}; the stream then has to be closed with {@link #close}. Requests ask for their version
 * with {@link #get}, which waits for versions that are still to come.
 * <p>
 * The stream methods are called by one thread, {@link #get} by many.
 */
final class TimetableVersions {
    private static final Logger log = LogManager.getLogger(TimetableVersions.class);

    private record Key(int iteration, int snapshotId) {
    }

    // all fields are guarded by this
    /**
     * Builds snapshot 0 until the first iteration starts, null afterwards.
     */
    private VersionedRaptorTimetable.Builder builder;
    private int baseRoutes = 0;
    private int baseDepartures = 0;
    private VersionedRaptorTimetable base;

    private boolean started = false;
    private int iteration;
    private int latestSnapshot;
    private int oldestSnapshotNeeded;
    /**
     * The versions of the current iteration that may still be asked for, by snapshot id.
     */
    private final NavigableMap<Integer, VersionedRaptorTimetable> timetableVersions = new TreeMap<>();
    /**
     * Requests that wait for a version that has not arrived yet, by (iteration, snapshot id). {@link #get} files a
     * request here if its version is
     * <ul>
     *     <li>a snapshot after {@link #latestSnapshot} of the current iteration,</li>
     *     <li>any snapshot of a later iteration, or</li>
     *     <li>any snapshot while snapshot 0 is still being built (before the first iteration starts).</li>
     * </ul>
     * All requests for the same version share one future. {@link #get} returns a copy of it to each caller, so that a
     * timeout or a cancellation of one caller does not complete the shared future for the others.
     * <p>
     * An entry is removed when {@link #settlePending} decides it, after the stream message that brings its version or
     * starts a later iteration, or when {@link #close} fails it. It is not removed when all its callers have given up
     * (e.g. after a timeout); it then stays until one of these events.
     */
    private final Map<Key, CompletableFuture<VersionedRaptorTimetable>> pending = new HashMap<>();
    /**
     * Why the store was closed, null while it is open.
     */
    private RuntimeException closed;

    /**
     * @throws IllegalStateException if {@code data} was not created with {@code useTimetableUpdates}
     */
    TimetableVersions(SwissRailRaptorData data) {
        this.builder = VersionedRaptorTimetable.builder(data);
    }

    /**
     * Adds a route of snapshot 0 with all its departures.
     */
    synchronized void addBaseRoute(BaseRoute route) {
        requireOpen();
        if (this.builder == null) {
            throw new IllegalStateException("Route " + route.getTransitRouteId() + " of line " + route.getTransitLineId()
                    + " of snapshot 0 arrived after the start of iteration " + this.iteration + ".");
        }
        List<Id<TransitStopFacility>> stops = new ArrayList<>(route.getStopFacilityIdsCount());
        for (String stop : route.getStopFacilityIdsList()) {
            stops.add(Id.create(stop, TransitStopFacility.class));
        }
        this.builder.addRoute(Id.create(route.getTransitLineId(), TransitLine.class), Id.create(route.getTransitRouteId(), TransitRoute.class), stops);
        for (BaseDeparture departure : route.getDeparturesList()) {
            this.builder.addDeparture(Id.create(departure.getDepartureId(), Departure.class),
                    seconds(departure.getArrivalTimesNsCount(), departure::getArrivalTimesNs),
                    seconds(departure.getDepartureTimesNsCount(), departure::getDepartureTimesNs));
        }
        this.baseRoutes++;
        this.baseDepartures += route.getDeparturesCount();
    }

    /**
     * Starts an iteration on snapshot 0. The first call completes snapshot 0, every later one must start the next
     * iteration. Requests for versions of earlier iterations fail.
     */
    void startIteration(int iteration) {
        List<Runnable> settled;
        synchronized (this) {
            requireOpen();
            if (this.builder != null) {
                long start = System.nanoTime();
                this.base = this.builder.build();
                this.builder = null;
                log.info("Snapshot 0 complete: {} routes with {} departures, built in {} ms", this.baseRoutes, this.baseDepartures,
                        (System.nanoTime() - start) / 1_000_000);
            } else if (iteration != this.iteration + 1) {
                throw new IllegalArgumentException("Iteration " + iteration + " starts after iteration " + this.iteration + ", expected iteration "
                        + (this.iteration + 1) + ".");
            }
            this.started = true;
            this.iteration = iteration;
            this.latestSnapshot = 0;
            this.oldestSnapshotNeeded = 0;
            this.timetableVersions.clear();
            this.timetableVersions.put(0, this.base);
            settled = settlePending();
        }
        settled.forEach(Runnable::run);
        log.info("Iteration {} started on snapshot 0", iteration);
    }

    /**
     * Applies the delta of the next snapshot of the current iteration and releases the versions no longer needed.
     */
    void applyDelta(TimetableDelta delta) {
        List<Runnable> settled;
        synchronized (this) {
            requireOpen();
            int k = delta.getSnapshotId();
            if (!this.started) {
                throw new IllegalStateException("The delta of snapshot " + k + " arrived before the first iteration started.");
            }
            if (delta.getIteration() != this.iteration) {
                throw new IllegalArgumentException("The delta of snapshot " + k + " is for iteration " + delta.getIteration() + ", but iteration "
                        + this.iteration + " is running.");
            }
            if (k != this.latestSnapshot + 1) {
                throw new IllegalArgumentException("Snapshot " + k + " of iteration " + this.iteration + " follows snapshot " + this.latestSnapshot
                        + ", expected snapshot " + (this.latestSnapshot + 1) + ".");
            }
            int oldest = delta.getOldestNeededSnapshotId();
            if (oldest > k || oldest < this.oldestSnapshotNeeded) {
                throw new IllegalArgumentException("Snapshot " + k + " of iteration " + this.iteration + " names " + oldest
                        + " as the oldest needed snapshot, which must be between " + this.oldestSnapshotNeeded + " and " + k + ".");
            }
            List<TripUpdate> trips = new ArrayList<>(delta.getTripsCount());
            for (org.matsim.schemas.services.routing.v1.TripUpdate trip : delta.getTripsList()) {
                trips.add(new TripUpdate(trip.getDeparture(), trip.getFromStop(),
                        seconds(trip.getArrivalTimesNsCount(), trip::getArrivalTimesNs),
                        seconds(trip.getDepartureTimesNsCount(), trip::getDepartureTimesNs)));
            }
            VersionedRaptorTimetable previous = this.timetableVersions.get(this.latestSnapshot);
            VersionedRaptorTimetable version;
            try {
                version = trips.isEmpty() ? previous : previous.apply(trips);
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException("Snapshot " + k + " of iteration " + this.iteration + ": " + e.getMessage(), e);
            }
            this.timetableVersions.put(k, version);
            this.latestSnapshot = k;
            this.oldestSnapshotNeeded = oldest;
            this.timetableVersions.headMap(oldest).clear();
            settled = settlePending();
            log.debug("Snapshot {} of iteration {}: {} changed departures, oldest needed snapshot {}", k, this.iteration, trips.size(), oldest);
        }
        settled.forEach(Runnable::run);
    }

    /**
     * @return the version {@code snapshotId} of {@code iteration}: completed if it is there, pending if it is still to
     * come, and failed with an {@link IllegalStateException} if it was released, belongs to an iteration that has
     * ended, or the store was closed. Each call gets its own future, so a caller may add a timeout or cancel it.
     */
    CompletableFuture<VersionedRaptorTimetable> get(int iteration, int snapshotId) {
        synchronized (this) {
            if (this.closed != null) {
                return CompletableFuture.failedFuture(new IllegalStateException(describe(iteration, snapshotId)
                        + " is not available: " + this.closed.getMessage(), this.closed));
            }
            if (this.started && iteration < this.iteration) {
                return CompletableFuture.failedFuture(new IllegalStateException(describe(iteration, snapshotId)
                        + " is not available: iteration " + this.iteration + " is running."));
            }
            if (this.started && iteration == this.iteration && snapshotId <= this.latestSnapshot) {
                if (snapshotId < this.oldestSnapshotNeeded) {
                    return CompletableFuture.failedFuture(new IllegalStateException(describe(iteration, snapshotId)
                            + " was released, the oldest needed snapshot is " + this.oldestSnapshotNeeded + "."));
                }
                return CompletableFuture.completedFuture(this.timetableVersions.get(snapshotId));
            }
            return this.pending.computeIfAbsent(new Key(iteration, snapshotId), _ -> new CompletableFuture<>()).copy();
        }
    }

    /**
     * Closes the store: pending and later requests fail with {@code cause}. Only the first call has an effect.
     */
    void close(RuntimeException cause) {
        List<CompletableFuture<VersionedRaptorTimetable>> failing;
        synchronized (this) {
            if (this.closed != null) {
                return;
            }
            this.closed = cause;
            failing = new ArrayList<>(this.pending.values());
            this.pending.clear();
            this.timetableVersions.clear();
            this.builder = null;
            this.base = null;
        }
        for (CompletableFuture<VersionedRaptorTimetable> future : failing) {
            future.completeExceptionally(new IllegalStateException("The timetable version is not available: " + cause.getMessage(), cause));
        }
    }

    private void requireOpen() {
        if (this.closed != null) {
            throw new IllegalStateException("The timetable versions are closed: " + this.closed.getMessage(), this.closed);
        }
    }

    /**
     * Decides the waiting requests in {@link #pending} that the new state allows to decide, and removes them. Called
     * under the lock at the end of {@link #startIteration} and {@link #applyDelta}, i.e. after each stream message
     * that changes the iteration or the latest snapshot.
	 *
     * The futures are not completed here. The decisions are returned as actions that the caller runs after it has
     * released the lock: completing a future runs the callbacks of the waiting requests that were added without an
     * executor in the completing thread, the stream thread. They must not run under the lock, and should not be long
     * work such as routing, which the callers have to move to their own executor.
     */
    private List<Runnable> settlePending() {
        List<Runnable> settled = new ArrayList<>();
        Iterator<Map.Entry<Key, CompletableFuture<VersionedRaptorTimetable>>> entries = this.pending.entrySet().iterator();
        while (entries.hasNext()) {
            Map.Entry<Key, CompletableFuture<VersionedRaptorTimetable>> entry = entries.next();
            Key key = entry.getKey();
            CompletableFuture<VersionedRaptorTimetable> future = entry.getValue();
            if (key.iteration() < this.iteration) {
                String message = describe(key.iteration(), key.snapshotId()) + " never arrived: iteration " + this.iteration + " started.";
                settled.add(() -> future.completeExceptionally(new IllegalStateException(message)));
            } else if (key.iteration() == this.iteration && key.snapshotId() <= this.latestSnapshot) {
                VersionedRaptorTimetable version = this.timetableVersions.get(key.snapshotId());
                settled.add(() -> future.complete(version));
            } else {
                continue;
            }
            entries.remove();
        }
        return settled;
    }

    private static String describe(int iteration, int snapshotId) {
        return "Snapshot " + snapshotId + " of iteration " + iteration;
    }

    private static int[] seconds(int count, IntToLongFunction ns) {
        int[] seconds = new int[count];
        for (int i = 0; i < count; i++) {
            seconds[i] = wholeSeconds(ns.applyAsLong(i));
        }
        return seconds;
    }
}
