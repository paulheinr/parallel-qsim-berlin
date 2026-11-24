package org.matsim.routing;

import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptor;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Coord;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.Activity;
import org.matsim.api.core.v01.population.Leg;
import org.matsim.api.core.v01.population.PlanElement;
import org.matsim.application.MATSimAppCommand;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.router.DefaultRoutingRequest;
import org.matsim.core.router.RoutingRequest;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.utils.io.IOUtils;
import org.matsim.core.utils.misc.OptionalTime;
import org.matsim.core.utils.misc.Time;
import org.matsim.facilities.ActivityFacilitiesFactoryImpl;
import org.matsim.facilities.ActivityFacility;
import org.matsim.facilities.Facility;
import org.matsim.pt.routes.TransitPassengerRoute;
import org.matsim.routing.RaptorVariants.Variant;
import org.matsim.utils.objectattributes.attributable.AttributesImpl;
import picocli.CommandLine;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;

/**
 * Step B6 of the design doc on exogenous pt delays: routes a fixed sample of the pt trips of Berlin 1pct with one
 * {@link Variant} of SwissRailRaptor, in one thread, and writes the routing times and the routes. Not a JUnit test.
 * <p>
 * {@code scripts/raptor-benchmark/run.sh} runs it with the matsim jars from before and after the timetable updates, for all
 * variants and several forks. Every run appends to {@code rounds.csv} and writes its own files, see {@link #call()}.
 * The requests are built like in {@link RoutingService}: a facility at the link and the coordinate of each end of the
 * trip, its departure time and no person. All variants route without the routes that arrive at a stop before they
 * depart from the previous one ({@link RaptorVariants#removeRoutesRunningBackwards}).
 */
@CommandLine.Command(name = "raptor-benchmark", description = "Routing time of a variant of SwissRailRaptor on a sample of pt trips")
public final class RaptorBenchmark implements MATSimAppCommand {
    private static final Logger log = LogManager.getLogger(RaptorBenchmark.class);

    @CommandLine.Option(names = "--config", description = "Router config", defaultValue = "integration/berlin/router-config.xml")
    private Path config;

    @CommandLine.Option(names = "--trips", description = "Trips file of the calibrated run, whose pt trips are sampled",
            defaultValue = "../../public-svn/matsim/scenarios/countries/de/berlin/berlin-v7.1/calibrated-1pct/output/berlin-v7.1-1pct.output_trips.csv.gz")
    private Path trips;

    @CommandLine.Option(names = "--sample", description = "Number of pt trips to route", defaultValue = "2000")
    private int sample;

    @CommandLine.Option(names = "--seed", description = "Seed of the sample", defaultValue = "1")
    private long seed;

    @CommandLine.Option(names = "--variant", description = "schedule, option or versioned", required = true)
    private String variant;

    @CommandLine.Option(names = "--label", description = "Name of the matsim jar, e.g. base or branch", required = true)
    private String label;

    @CommandLine.Option(names = "--warmup", description = "Rounds before the measurement", defaultValue = "3")
    private int warmup;

    @CommandLine.Option(names = "--rounds", description = "Measured rounds", defaultValue = "10")
    private int rounds;

    @CommandLine.Option(names = "--fork", description = "Number of this run among the runs of the same label and variant", defaultValue = "1")
    private int fork;

    @CommandLine.Option(names = "--output", description = "Output directory", required = true)
    private Path output;

    public static void main(String[] args) {
        new RaptorBenchmark().execute(args);
    }

    /**
     * Writes to {@code --output}:
     * <ul>
     *     <li>{@code rounds.csv}: the wall time of each round, appended;</li>
     *     <li>{@code requests-<label>-<variant>-<fork>.csv}: per trip the median and the minimum of its routing time over
     *     the measured rounds;</li>
     *     <li>{@code routes-<label>-<variant>-<fork>.tsv}: per trip the route of the last round;</li>
     *     <li>{@code run-<label>-<variant>-<fork>.json}: the settings, the JVM, the matsim jar and the setup times.</li>
     * </ul>
     */
    @Override
    public Integer call() throws Exception {
        Variant variant = Variant.valueOf(this.variant.toUpperCase(Locale.ROOT));
        String name = this.label + "-" + variant.name().toLowerCase(Locale.ROOT) + "-" + this.fork;
        Files.createDirectories(this.output);

        long start = System.nanoTime();
        Config config = ConfigUtils.loadConfig(this.config.toString());
        Scenario scenario = ScenarioUtils.loadScenario(config);
        int removedRoutes = RaptorVariants.removeRoutesRunningBackwards(scenario.getTransitSchedule());
        long loaded = System.nanoTime();
        SwissRailRaptor raptor = RaptorVariants.create(config, scenario, variant);
        long created = System.nanoTime();

        List<Trip> sample = sample(readPtTrips(this.trips), this.sample, this.seed);
        List<RoutingRequest> requests = sample.stream().map(Trip::request).toList();
        log.info("Routing {} pt trips with {} of {}: {} warm-up and {} measured rounds", requests.size(), variant, this.label, this.warmup, this.rounds);

        long[][] times = new long[this.rounds][requests.size()];
        List<?>[] routes = new List<?>[requests.size()];
        long sink = 0;
        for (int round = 0; round < this.warmup + this.rounds; round++) {
            boolean measured = round >= this.warmup;
            long roundStart = System.nanoTime();
            for (int i = 0; i < requests.size(); i++) {
                long t0 = System.nanoTime();
                List<? extends PlanElement> route = raptor.calcRoute(requests.get(i));
                long t1 = System.nanoTime();
                if (measured) {
                    times[round - this.warmup][i] = t1 - t0;
                }
                routes[i] = route;
                sink += route == null ? 0 : route.size();
            }
            long total = System.nanoTime() - roundStart;
            appendRound(round, measured, requests.size(), total);
            log.info("Round {} ({}): {} ms, {} us per request", round, measured ? "measured" : "warm-up", total / 1_000_000, total / 1000 / requests.size());
        }
        log.info("Routes found: {} plan elements in total", sink);

        writeRequests(this.output.resolve("requests-" + name + ".csv"), sample, times);
        writeRoutes(this.output.resolve("routes-" + name + ".tsv"), sample, routes);
        writeRun(this.output.resolve("run-" + name + ".json"), variant, removedRoutes, (loaded - start) / 1e9, (created - loaded) / 1e9);
        return 0;
    }

    /**
     * A pt trip of the trips file.
     */
    record Trip(String id, double departureTime, Id<Link> fromLink, Coord from, Id<Link> toLink, Coord to) {

        RoutingRequest request() {
            return DefaultRoutingRequest.of(facility("fromFacility", this.from, this.fromLink), facility("toFacility", this.to, this.toLink),
                    this.departureTime, null, new AttributesImpl());
        }

        private static Facility facility(String id, Coord coord, Id<Link> link) {
            return new ActivityFacilitiesFactoryImpl().createActivityFacility(Id.create(id, ActivityFacility.class), coord, link);
        }
    }

    /**
     * @return the trips with main mode pt, sorted by trip id
     */
    static List<Trip> readPtTrips(Path file) throws IOException {
        List<Trip> trips = new ArrayList<>();
        try (BufferedReader reader = IOUtils.getBufferedReader(file.toString())) {
            Map<String, Integer> column = new HashMap<>();
            String[] header = reader.readLine().split(";", -1);
            for (int i = 0; i < header.length; i++) {
                column.put(header[i], i);
            }
            String line;
            while ((line = reader.readLine()) != null) {
                String[] f = line.split(";", -1);
                if (!f[column.get("main_mode")].equals("pt")) {
                    continue;
                }
                trips.add(new Trip(f[column.get("trip_id")], Time.parseTime(f[column.get("dep_time")]),
                        Id.createLinkId(f[column.get("start_link")]),
                        new Coord(Double.parseDouble(f[column.get("start_x")]), Double.parseDouble(f[column.get("start_y")])),
                        Id.createLinkId(f[column.get("end_link")]),
                        new Coord(Double.parseDouble(f[column.get("end_x")]), Double.parseDouble(f[column.get("end_y")]))));
            }
        }
        trips.sort(Comparator.comparing(Trip::id));
        return trips;
    }

    /**
     * @return {@code size} of the trips, drawn with {@code seed}, in random order
     */
    static List<Trip> sample(List<Trip> trips, int size, long seed) {
        List<Trip> shuffled = new ArrayList<>(trips);
        Collections.shuffle(shuffled, new Random(seed));
        return List.copyOf(shuffled.subList(0, Math.min(size, shuffled.size())));
    }

    /**
     * A route as one line: per leg its mode, departure and travel time, and for pt legs line, route, access and egress
     * stop and boarding time. {@code none} if the raptor found no route.
     */
    static String signature(List<?> route) {
        if (route == null) {
            return "none";
        }
        StringJoiner elements = new StringJoiner(" ");
        for (Object element : route) {
            if (element instanceof Leg leg) {
                StringBuilder s = new StringBuilder(leg.getMode()).append('@').append(seconds(leg.getDepartureTime())).append('+')
                        .append(seconds(leg.getTravelTime()));
                if (leg.getRoute() instanceof TransitPassengerRoute pt) {
                    s.append('[').append(pt.getLineId()).append('/').append(pt.getRouteId()).append(':').append(pt.getAccessStopId()).append('>')
                            .append(pt.getEgressStopId()).append('@').append(seconds(pt.getBoardingTime())).append(']');
                }
                elements.add(s);
            } else if (element instanceof Activity activity) {
                elements.add(activity.getType());
            }
        }
        return elements.toString();
    }

    /**
     * @return the arrival of the route (end of its last leg) in seconds, -1 if there is no route or it is unknown
     */
    static double arrival(List<?> route) {
        if (route == null) {
            return -1;
        }
        for (int i = route.size() - 1; i >= 0; i--) {
            if (route.get(i) instanceof Leg leg) {
                if (leg.getDepartureTime().isUndefined() || leg.getTravelTime().isUndefined()) {
                    return -1;
                }
                return leg.getDepartureTime().seconds() + leg.getTravelTime().seconds();
            }
        }
        return -1;
    }

    private static String seconds(OptionalTime time) {
        return time.isDefined() ? Long.toString(Math.round(time.seconds())) : "-";
    }

    private void appendRound(int round, boolean measured, int requests, long totalNs) throws IOException {
        Path file = this.output.resolve("rounds.csv");
        boolean header = Files.notExists(file);
        try (BufferedWriter writer = Files.newBufferedWriter(file, StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
            if (header) {
                writer.write("label,variant,fork,round,measured,requests,total_ns\n");
            }
            writer.write(String.join(",", this.label, this.variant.toLowerCase(Locale.ROOT), Integer.toString(this.fork), Integer.toString(round),
                    Boolean.toString(measured), Integer.toString(requests), Long.toString(totalNs)) + "\n");
        }
    }

    private static void writeRequests(Path file, List<Trip> sample, long[][] times) throws IOException {
        try (BufferedWriter writer = Files.newBufferedWriter(file)) {
            writer.write("trip_id,median_ns,min_ns\n");
            long[] perRequest = new long[times.length];
            for (int i = 0; i < sample.size(); i++) {
                for (int round = 0; round < times.length; round++) {
                    perRequest[round] = times[round][i];
                }
                Arrays.sort(perRequest);
                long median = perRequest.length % 2 == 1 ? perRequest[perRequest.length / 2]
                        : (perRequest[perRequest.length / 2 - 1] + perRequest[perRequest.length / 2]) / 2;
                writer.write(sample.get(i).id() + "," + median + "," + perRequest[0] + "\n");
            }
        }
    }

    private static void writeRoutes(Path file, List<Trip> sample, List<?>[] routes) throws IOException {
        try (BufferedWriter writer = Files.newBufferedWriter(file)) {
            writer.write("trip_id\tdep_time\tarrival\tpt_legs\troute\n");
            for (int i = 0; i < sample.size(); i++) {
                List<?> route = routes[i];
                long ptLegs = route == null ? 0
                        : route.stream().filter(e -> e instanceof Leg leg && leg.getRoute() instanceof TransitPassengerRoute).count();
                writer.write(sample.get(i).id() + "\t" + Math.round(sample.get(i).departureTime()) + "\t" + Math.round(arrival(route)) + "\t" + ptLegs
                        + "\t" + signature(route) + "\n");
            }
        }
    }

    private void writeRun(Path file, Variant variant, int removedRoutes, double loadS, double createS) throws IOException, NoSuchAlgorithmException {
        String jar = "";
        String sha256 = "";
        try {
            Path location = Path.of(SwissRailRaptor.class.getProtectionDomain().getCodeSource().getLocation().toURI());
            jar = location.toString();
            if (Files.isRegularFile(location)) {
                sha256 = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(location)));
            }
        } catch (Exception e) {
            log.warn("Could not locate the matsim jar", e);
        }
        String json = String.format(Locale.ROOT, """
                        {"label": "%s", "variant": "%s", "fork": %d, "sample": %d, "seed": %d, "warmup": %d, "rounds": %d,
                         "java_version": "%s", "java_vm": "%s", "max_heap_mb": %d, "matsim_jar": "%s", "matsim_jar_sha256": "%s",
                         "removed_routes": %d, "load_s": %.3f, "create_raptor_s": %.3f}
                        """, this.label, variant.name().toLowerCase(Locale.ROOT), this.fork, this.sample, this.seed, this.warmup, this.rounds,
                System.getProperty("java.version"), System.getProperty("java.vm.name"), Runtime.getRuntime().maxMemory() / 1024 / 1024, jar, sha256,
                removedRoutes, loadS, createS);
        Files.writeString(file, json);
    }
}
