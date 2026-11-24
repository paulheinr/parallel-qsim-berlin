package org.matsim.routing;

import org.matsim.pt.transitSchedule.api.Departure;
import org.matsim.pt.transitSchedule.api.TransitLine;
import org.matsim.pt.transitSchedule.api.TransitRoute;
import org.matsim.pt.transitSchedule.api.TransitRouteStop;
import org.matsim.pt.transitSchedule.api.TransitSchedule;
import org.matsim.schemas.services.routing.v1.BaseDeparture;
import org.matsim.schemas.services.routing.v1.BaseRoute;
import org.matsim.schemas.services.routing.v1.IterationStart;
import org.matsim.schemas.services.routing.v1.TimetableDelta;
import org.matsim.schemas.services.routing.v1.TimetableUpdate;
import org.matsim.schemas.services.routing.v1.TimetableVersion;
import org.matsim.schemas.services.routing.v1.TripUpdate;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Messages of the timetable stream for tests: snapshot 0 from a transit schedule, iteration starts, deltas and versions.
 */
final class TimetableMessages {

    private TimetableMessages() {
    }

    /**
     * Snapshot 0 from the schedule: per route its stops, and its departures sorted by start time with start plus offsets.
     */
    record SnapshotZero(List<TimetableUpdate> messages, List<Trip> trips) {

        /**
         * A departure with its number in snapshot 0 (its index in {@link #trips}).
         */
        record Trip(TransitRoute route, Departure departure, int[] arrivals, int[] departures) {
        }

        SnapshotZero(TransitSchedule schedule) {
            this(new ArrayList<>(), new ArrayList<>());
            for (TransitLine line : schedule.getTransitLines().values()) {
                for (TransitRoute route : line.getRoutes().values()) {
                    BaseRoute.Builder message = BaseRoute.newBuilder().setTransitLineId(line.getId().toString()).setTransitRouteId(route.getId().toString());
                    route.getStops().forEach(stop -> message.addStopFacilityIds(stop.getStopFacility().getId().toString()));
                    List<Departure> departures = new ArrayList<>(route.getDepartures().values());
                    departures.sort(Comparator.comparingDouble(Departure::getDepartureTime).thenComparing(d -> d.getId().toString()));
                    for (Departure departure : departures) {
                        int start = (int) departure.getDepartureTime();
                        int[] arrivals = new int[route.getStops().size()];
                        int[] departureTimes = new int[route.getStops().size()];
                        BaseDeparture.Builder base = BaseDeparture.newBuilder().setDepartureId(departure.getId().toString());
                        for (int i = 0; i < arrivals.length; i++) {
                            TransitRouteStop stop = route.getStops().get(i);
                            arrivals[i] = start + (int) stop.getArrivalOffset().or(stop::getDepartureOffset).seconds();
                            departureTimes[i] = start + (int) stop.getDepartureOffset().or(stop::getArrivalOffset).seconds();
                            base.addArrivalTimesNs(ns(arrivals[i])).addDepartureTimesNs(ns(departureTimes[i]));
                        }
                        message.addDepartures(base);
                        this.trips.add(new Trip(route, departure, arrivals, departureTimes));
                    }
                    this.messages.add(TimetableUpdate.newBuilder().setBaseRoute(message).build());
                }
            }
        }

        /**
         * @return the number of the departure of {@code routeId} that leaves {@code stopId} at {@code time}
         */
        int external(String routeId, String stopId, int time) {
            for (int t = 0; t < this.trips.size(); t++) {
                Trip trip = this.trips.get(t);
                if (trip.route().getId().toString().equals(routeId)) {
                    for (int i = 0; i < trip.departures().length; i++) {
                        if (trip.route().getStops().get(i).getStopFacility().getId().toString().equals(stopId) && trip.departures()[i] == time) {
                            return t;
                        }
                    }
                }
            }
            throw new AssertionError("No departure of route " + routeId + " leaves " + stopId + " at " + time);
        }

        /**
         * @return the number of the departure with id {@code departureId}
         */
        int external(String departureId) {
            for (int t = 0; t < this.trips.size(); t++) {
                if (this.trips.get(t).departure().getId().toString().equals(departureId)) {
                    return t;
                }
            }
            throw new AssertionError("No departure " + departureId);
        }

        /**
         * @return the times of departure {@code external}, {@code delay} seconds later at all stops
         */
        TripUpdate delayed(int external, int delay) {
            Trip trip = this.trips.get(external);
            TripUpdate.Builder update = TripUpdate.newBuilder().setDeparture(external).setFromStop(0);
            for (int i = 0; i < trip.arrivals().length; i++) {
                update.addArrivalTimesNs(ns(trip.arrivals()[i] + delay)).addDepartureTimesNs(ns(trip.departures()[i] + delay));
            }
            return update.build();
        }

        /**
         * @return the times of the departure with id {@code departureId}, {@code delay} seconds later at all stops
         */
        TripUpdate delayed(String departureId, int delay) {
            return delayed(external(departureId), delay);
        }
    }

    static TimetableUpdate start(int iteration) {
        return TimetableUpdate.newBuilder().setIterationStart(IterationStart.newBuilder().setIteration(iteration)).build();
    }

    static TimetableUpdate delta(int iteration, int snapshotId, int oldestNeeded, TripUpdate... trips) {
        return TimetableUpdate.newBuilder().setDelta(TimetableDelta.newBuilder().setIteration(iteration).setSnapshotId(snapshotId)
                .setOldestNeededSnapshotId(oldestNeeded).addAllTrips(List.of(trips))).build();
    }

    static TimetableVersion version(int iteration, int snapshotId) {
        return TimetableVersion.newBuilder().setIteration(iteration).setSnapshotId(snapshotId).build();
    }

    static long ns(int seconds) {
        return seconds * RoutingUtils.NANOS_PER_SECOND;
    }
}
