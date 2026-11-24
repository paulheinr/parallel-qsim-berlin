package org.matsim.routing;

import ch.sbb.matsim.config.SwissRailRaptorConfigGroup;
import ch.sbb.matsim.routing.pt.raptor.RaptorUtils;
import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptorData;
import ch.sbb.matsim.routing.pt.raptor.VersionedRaptorTimetable;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Scenario;
import org.matsim.application.MATSimAppCommand;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.utils.misc.Time;
import org.matsim.routing.TimetableMessages.SnapshotZero;
import org.matsim.routing.TimetableMessages.SnapshotZero.Trip;
import org.matsim.schemas.services.routing.v1.TimetableDelta;
import org.matsim.schemas.services.routing.v1.TimetableUpdate;
import org.matsim.schemas.services.routing.v1.TripUpdate;
import picocli.CommandLine;

import java.io.BufferedWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

import static org.matsim.routing.TimetableMessages.delta;
import static org.matsim.routing.TimetableMessages.ns;

/**
 * Step B6 of the design doc on exogenous pt delays: what the router spends on snapshot 0 and on the deltas of the
 * timetable stream, on the transit schedule of Berlin. Not a JUnit test; needs the matsim jar with the timetable
 * updates.
 * <p>
 * Snapshot 0 is built from the schedule ({@link SnapshotZero}), without the routes that arrive at a stop before they
 * depart from the previous one ({@link RaptorVariants#removeRoutesRunningBackwards}), and sent through
 * {@link TimetableVersions} as the router receives it. Then, in each of several iterations, a delta per interval around the peak of the schedule (the time with
 * the most running departures), see {@link DelayGenerator}. Per delta, the benchmark measures the router path without
 * the gRPC transport (parsing the message and {@link TimetableVersions#applyDelta}), the parsing alone and
 * {@link VersionedRaptorTimetable#apply} alone, and compares them with the budget interval / real-time ratio. It also
 * parses the same delta with shorter numbers in the time fields ({@link Encoding}), to see how much shorter times would
 * save; these messages are only parsed, not applied.
 */
@CommandLine.Command(name = "timetable-update-benchmark", description = "Cost of snapshot 0 and of the deltas of the timetable stream")
public final class TimetableUpdateBenchmark implements MATSimAppCommand {
    private static final Logger log = LogManager.getLogger(TimetableUpdateBenchmark.class);

    @CommandLine.Option(names = "--config", description = "Router config", defaultValue = "integration/berlin/router-config.xml")
    private Path config;

    @CommandLine.Option(names = "--deltas", description = "Deltas per iteration", defaultValue = "60")
    private int deltas;

    @CommandLine.Option(names = "--interval", description = "Simulated seconds between two snapshots", defaultValue = "60")
    private int interval;

    @CommandLine.Option(names = "--max-delay", description = "Largest delay of a running departure in s", defaultValue = "180")
    private int maxDelay;

    @CommandLine.Option(names = "--window", description = "Versions that stay alive (oldest needed snapshot = k - window)", defaultValue = "10")
    private int window;

    @CommandLine.Option(names = "--iterations", description = "Iterations, each with all deltas", defaultValue = "5")
    private int iterations;

    @CommandLine.Option(names = "--warmup-iterations", description = "Iterations that are not measured", defaultValue = "2")
    private int warmupIterations;

    @CommandLine.Option(names = "--rtr", description = "Real-time ratio of the simulation for the budget", defaultValue = "50000")
    private double rtr;

    @CommandLine.Option(names = "--seed", description = "Seed of the delays", defaultValue = "1")
    private long seed;

    @CommandLine.Option(names = "--output", description = "Output directory", required = true)
    private Path output;

    public static void main(String[] args) {
        new TimetableUpdateBenchmark().execute(args);
    }

    /**
     * Writes {@code snapshot0.json} and {@code updates.csv} (one row per delta) to {@code --output}.
     */
    @Override
    public Integer call() throws Exception {
        Files.createDirectories(this.output);
        Config config = ConfigUtils.loadConfig(this.config.toString());
        ConfigUtils.addOrGetModule(config, SwissRailRaptorConfigGroup.class).setUseTimetableUpdates(true);
        Scenario scenario = ScenarioUtils.loadScenario(config);
        int removedRoutes = RaptorVariants.removeRoutesRunningBackwards(scenario.getTransitSchedule());
        SwissRailRaptorData data = SwissRailRaptorData.create(scenario.getTransitSchedule(), scenario.getTransitVehicles(),
                RaptorUtils.createStaticConfig(config), scenario.getNetwork(), null);

        SnapshotZero snapshot = new SnapshotZero(scenario.getTransitSchedule());
        long messageBytes = 0;
        long largestMessage = 0;
        for (TimetableUpdate message : snapshot.messages()) {
            messageBytes += message.getSerializedSize();
            largestMessage = Math.max(largestMessage, message.getSerializedSize());
        }
        long start = System.nanoTime();
        TimetableVersions versions = new TimetableVersions(data);
        for (TimetableUpdate message : snapshot.messages()) {
            versions.addBaseRoute(message.getBaseRoute());
        }
        versions.startIteration(0);
        double snapshotZeroS = (System.nanoTime() - start) / 1e9;

        DelayGenerator delays = new DelayGenerator(snapshot.trips(), this.maxDelay, new Random(this.seed));
        int peak = delays.peak();
        int first = peak - this.deltas / 2 * this.interval;
        log.info("Snapshot 0: {} routes, {} departures, {} MB in messages (largest {} kB), built in {} s. Peak at {} with {} running departures.",
                snapshot.messages().size(), snapshot.trips().size(), messageBytes / 1_000_000, largestMessage / 1000, snapshotZeroS,
                Time.writeTime(peak), delays.running(peak));
        Files.writeString(this.output.resolve("snapshot0.json"), String.format(Locale.ROOT, """
                        {"routes": %d, "departures": %d, "removed_routes": %d, "message_bytes": %d, "largest_message_bytes": %d, "build_s": %.3f,
                         "peak": %d, "running_at_peak": %d, "first_delta_time": %d, "interval_s": %d, "rtr": %.0f, "budget_ns": %d}
                        """, snapshot.messages().size(), snapshot.trips().size(), removedRoutes, messageBytes, largestMessage, snapshotZeroS, peak,
                delays.running(peak),
                first + this.interval, this.interval, this.rtr, budgetNs()));

        try (BufferedWriter writer = Files.newBufferedWriter(this.output.resolve("updates.csv"))) {
            writer.write("iteration,snapshot,time,measured,trips,changed_stops,message_bytes,parse_ns,apply_delta_ns,parse_and_apply_delta_ns,apply_ns,"
                    + "version_bytes,message_bytes_seconds,parse_seconds_ns,message_bytes_delay,parse_delay_ns\n");
            List<Long> routerPath = new ArrayList<>();
            List<Long> parseOnly = new ArrayList<>();
            List<Long> applyOnly = new ArrayList<>();
            List<Long> parseSeconds = new ArrayList<>();
            List<Long> parseDelay = new ArrayList<>();
            for (int iteration = 0; iteration < this.iterations; iteration++) {
                if (iteration > 0) {
                    versions.startIteration(iteration);
                }
                delays.reset();
                boolean measured = iteration >= this.warmupIterations;
                for (int k = 1; k <= this.deltas; k++) {
                    int time = first + k * this.interval;
                    List<VersionedRaptorTimetable.TripUpdate> updates = delays.next(time);
                    int oldest = Math.max(0, k - this.window);
                    byte[] message = message(iteration, k, oldest, updates, Encoding.NS, snapshot.trips());
                    byte[] messageSeconds = message(iteration, k, oldest, updates, Encoding.SECONDS, snapshot.trips());
                    byte[] messageDelay = message(iteration, k, oldest, updates, Encoding.DELAY, snapshot.trips());

                    long t0 = System.nanoTime();
                    TimetableDelta delta = TimetableUpdate.parseFrom(message).getDelta();
                    long t1 = System.nanoTime();
                    versions.applyDelta(delta);
                    long t2 = System.nanoTime();
                    VersionedRaptorTimetable previous = versions.get(iteration, k - 1).join();
                    long t3 = System.nanoTime();
                    previous.apply(updates);
                    long t4 = System.nanoTime();
                    int tripsSeconds = TimetableUpdate.parseFrom(messageSeconds).getDelta().getTripsCount();
                    long t5 = System.nanoTime();
                    int tripsDelay = TimetableUpdate.parseFrom(messageDelay).getDelta().getTripsCount();
                    long t6 = System.nanoTime();
                    if (tripsSeconds != updates.size() || tripsDelay != updates.size()) {
                        throw new IllegalStateException("Parsed " + tripsSeconds + " and " + tripsDelay + " trips, expected " + updates.size() + ".");
                    }

                    if (measured) {
                        routerPath.add(t2 - t0);
                        parseOnly.add(t1 - t0);
                        applyOnly.add(t4 - t3);
                        parseSeconds.add(t5 - t4);
                        parseDelay.add(t6 - t5);
                    }
                    long changedStops = updates.stream().mapToLong(u -> u.arrivalTimes().length).sum();
                    writer.write(String.join(",", Integer.toString(iteration), Integer.toString(k), Integer.toString(time), Boolean.toString(measured),
                            Integer.toString(updates.size()), Long.toString(changedStops), Integer.toString(message.length), Long.toString(t1 - t0),
                            Long.toString(t2 - t1), Long.toString(t2 - t0), Long.toString(t4 - t3), Long.toString(delays.versionBytes(updates)),
                            Integer.toString(messageSeconds.length), Long.toString(t5 - t4), Integer.toString(messageDelay.length),
                            Long.toString(t6 - t5)) + "\n");
                }
            }
            log.info("Per delta, router path (parse and applyDelta): median {} us, max {} us; apply alone: median {} us, max {} us; budget {} us",
                    median(routerPath) / 1000, Collections.max(routerPath) / 1000, median(applyOnly) / 1000, Collections.max(applyOnly) / 1000,
                    budgetNs() / 1000);
            log.info("Parsing per delta, median: {} us with ns, {} us with seconds, {} us with delays in seconds", median(parseOnly) / 1000,
                    median(parseSeconds) / 1000, median(parseDelay) / 1000);
        }
        return 0;
    }

    private long budgetNs() {
        return Math.round(this.interval / this.rtr * 1e9);
    }

    private static long median(List<Long> values) {
        List<Long> sorted = new ArrayList<>(values);
        Collections.sort(sorted);
        return sorted.get(sorted.size() / 2);
    }

    /**
     * @return the serialized delta with {@code updates}, whose times are written as {@code encoding} says; {@code trips}
     * are those of snapshot 0, with the times of the schedule
     */
    private static byte[] message(int iteration, int snapshotId, int oldestNeeded, List<VersionedRaptorTimetable.TripUpdate> updates,
                                  Encoding encoding, List<Trip> trips) {
        return delta(iteration, snapshotId, oldestNeeded, updates.stream().map(update -> toProto(update, encoding, trips))
                .toArray(TripUpdate[]::new)).toByteArray();
    }

    private static TripUpdate toProto(VersionedRaptorTimetable.TripUpdate update, Encoding encoding, List<Trip> trips) {
        Trip scheduled = trips.get(update.departure());
        TripUpdate.Builder trip = TripUpdate.newBuilder().setDeparture(update.departure()).setFromStop(update.fromStop());
        for (int i = 0; i < update.arrivalTimes().length; i++) {
            int stop = update.fromStop() + i;
            trip.addArrivalTimesNs(encoding.encode(update.arrivalTimes()[i], scheduled.arrivals()[stop]))
                    .addDepartureTimesNs(encoding.encode(update.departureTimes()[i], scheduled.departures()[stop]));
        }
        return trip.build();
    }

    /**
     * What the time fields of a {@link TripUpdate} hold. Only {@link #NS} is the schema; the others put shorter numbers
     * into the same {@code uint64} fields, so that their varints are as long as in a field of whole seconds
     * ({@code uint32}) or of delays against the schedule in seconds ({@code sint32}, which zigzag-encodes small
     * delays in as many bytes).
     */
    enum Encoding {
        /** ns since midnight, as in the schema */
        NS,
        /** whole seconds since midnight */
        SECONDS,
        /** seconds after the time of the schedule; the delays of {@link DelayGenerator} are never negative */
        DELAY;

        long encode(int time, int scheduled) {
            return switch (this) {
                case NS -> ns(time);
                case SECONDS -> time;
                case DELAY -> {
                    if (time < scheduled) {
                        throw new IllegalArgumentException("Time " + time + " lies before the time of the schedule " + scheduled + ".");
                    }
                    yield time - scheduled;
                }
            };
        }
    }

    /**
     * Synthetic forecasts for the deltas. At each snapshot time, every running departure (it has left its first stop
     * and not yet reached its last) gets a new random delay of 0 to {@code maxDelay} s against the schedule, from its
     * next stop on. Departures of the same route behind it are pushed where they would overtake it: at each stop, a
     * departure arrives and departs no earlier than the one before it, as the no-overtaking contract of the simulation
     * guarantees. Stops that a departure has already passed keep their times, and no other time lies before the snapshot
     * time. A departure gets an update if its times differ from those of the previous snapshot, from the first stop
     * where they differ.
     */
    static final class DelayGenerator {
        private final List<Trip> trips;
        private final int maxDelay;
        private final Random random;
        /**
         * per route: the numbers of its departures in snapshot 0, in their order
         */
        private final List<int[]> routes = new ArrayList<>();
        private int[][] arrivals;
        private int[][] departures;

        DelayGenerator(List<Trip> trips, int maxDelay, Random random) {
            this.trips = trips;
            this.maxDelay = maxDelay;
            this.random = random;
            // the trips of snapshot 0 come route by route, each route in its order
            int begin = 0;
            for (int t = 1; t <= trips.size(); t++) {
                if (t == trips.size() || trips.get(t).route() != trips.get(begin).route()) {
                    int[] order = new int[t - begin];
                    for (int i = 0; i < order.length; i++) {
                        order[i] = begin + i;
                    }
                    this.routes.add(order);
                    begin = t;
                }
            }
            reset();
        }

        /**
         * Back to the times of the schedule, as at the start of an iteration.
         */
        void reset() {
            this.arrivals = new int[this.trips.size()][];
            this.departures = new int[this.trips.size()][];
            for (int t = 0; t < this.trips.size(); t++) {
                this.arrivals[t] = this.trips.get(t).arrivals().clone();
                this.departures[t] = this.trips.get(t).departures().clone();
            }
        }

        /**
         * @return the time with the most running departures of the schedule
         */
        int peak() {
            TreeMap<Integer, Integer> changes = new TreeMap<>();
            for (Trip trip : this.trips) {
                changes.merge(trip.departures()[0], 1, Integer::sum);
                changes.merge(trip.arrivals()[trip.arrivals().length - 1], -1, Integer::sum);
            }
            int running = 0;
            int most = -1;
            int peak = 0;
            for (Map.Entry<Integer, Integer> change : changes.entrySet()) {
                running += change.getValue();
                if (running > most) {
                    most = running;
                    peak = change.getKey();
                }
            }
            return peak;
        }

        /**
         * @return the number of departures of the schedule that run at {@code time}
         */
        int running(int time) {
            int running = 0;
            for (Trip trip : this.trips) {
                if (trip.departures()[0] <= time && trip.arrivals()[trip.arrivals().length - 1] > time) {
                    running++;
                }
            }
            return running;
        }

        /**
         * @return the updates of the snapshot at {@code time}, against the previous one
         */
        List<VersionedRaptorTimetable.TripUpdate> next(int time) {
            List<VersionedRaptorTimetable.TripUpdate> updates = new ArrayList<>();
            for (int[] order : this.routes) {
                int[] previousArrivals = null;
                int[] previousDepartures = null;
                for (int t : order) {
                    int[] arrivals = this.arrivals[t].clone();
                    int[] departures = this.departures[t].clone();
                    int stops = arrivals.length;
                    int from;
                    if (departures[0] > time) {
                        // not started: the times of the schedule, pushed by the departure before it
                        from = 0;
                        System.arraycopy(this.trips.get(t).arrivals(), 0, arrivals, 0, stops);
                        System.arraycopy(this.trips.get(t).departures(), 0, departures, 0, stops);
                    } else if (arrivals[stops - 1] > time) {
                        // running: a new delay from its next stop on
                        from = 1;
                        while (arrivals[from] <= time) {
                            from++;
                        }
                        int delay = this.random.nextInt(this.maxDelay + 1);
                        for (int s = from; s < stops; s++) {
                            arrivals[s] = this.trips.get(t).arrivals()[s] + delay;
                            departures[s] = this.trips.get(t).departures()[s] + delay;
                        }
                    } else {
                        // arrived at its last stop
                        from = stops;
                    }
                    for (int s = from; s < stops; s++) {
                        if (s > 0) {
                            arrivals[s] = Math.max(arrivals[s], Math.max(departures[s - 1], time));
                        }
                        if (previousArrivals != null) {
                            arrivals[s] = Math.max(arrivals[s], previousArrivals[s]);
                        }
                        departures[s] = Math.max(departures[s], Math.max(arrivals[s], time));
                        if (previousDepartures != null) {
                            departures[s] = Math.max(departures[s], previousDepartures[s]);
                        }
                    }
                    int changed = from;
                    while (changed < stops && arrivals[changed] == this.arrivals[t][changed] && departures[changed] == this.departures[t][changed]) {
                        changed++;
                    }
                    if (changed < stops) {
                        updates.add(new VersionedRaptorTimetable.TripUpdate(t, changed, Arrays.copyOfRange(arrivals, changed, stops),
                                Arrays.copyOfRange(departures, changed, stops)));
                    }
                    this.arrivals[t] = arrivals;
                    this.departures[t] = departures;
                    previousArrivals = arrivals;
                    previousDepartures = departures;
                }
            }
            return updates;
        }

        /**
         * @return the memory of a new version with {@code updates}: the array of rows, which every version copies, and
         * the rows of the changed departures. Estimated for compressed object pointers: 16 bytes per array header,
         * 4 per reference and per int, rounded up to 8 per array.
         */
        long versionBytes(List<VersionedRaptorTimetable.TripUpdate> updates) {
            long bytes = align(16 + 4L * this.trips.size());
            Set<Integer> changed = new HashSet<>();
            for (VersionedRaptorTimetable.TripUpdate update : updates) {
                if (changed.add(update.departure())) {
                    bytes += align(16 + 4L * 2 * this.trips.get(update.departure()).arrivals().length);
                }
            }
            return bytes;
        }

        private static long align(long bytes) {
            return (bytes + 7) / 8 * 8;
        }
    }
}
