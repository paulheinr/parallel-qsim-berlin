package org.matsim.routing;

import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptor;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.matsim.api.core.v01.Scenario;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.router.DefaultRoutingRequest;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.utils.misc.Time;
import org.matsim.pt.transitSchedule.api.*;
import org.matsim.routing.RaptorVariants.Variant;
import org.matsim.utils.objectattributes.attributable.AttributesImpl;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * On the small scenarios in {@code integration/}, all {@link Variant}s of SwissRailRaptor find the same routes: the
 * option {@code useTimetableUpdates} and the versioned times of snapshot 0 change no result while the times are those
 * of the schedule. The Berlin sample of {@link RaptorBenchmark} checks the same on a large schedule.
 */
class RaptorVariantsTest {

    /**
     * The scenarios with the step between the departure times of the requests, in s.
     */
    static Stream<Arguments> scenarios() {
        return Stream.of(Arguments.of("pt-tutorial-dummy", 5 * 60), Arguments.of("pt-delays", 60));
    }

    /**
     * Routes between all pairs of stop facilities, from 10 min before the first departure of the schedule to its last
     * departure, with each variant, and compares the routes with those of {@link Variant#SCHEDULE}.
     */
    @ParameterizedTest(name = "{0}")
    @MethodSource("scenarios")
    void allVariantsFindTheSameRoutes(String scenario, int step) {
        Path config = Path.of("integration", scenario, "input", "router-config.xml");
        List<String> requests = null;
        List<String> schedule = null;
        for (Variant variant : Variant.values()) {
            Routes routes = route(config, variant, step);
            if (variant == Variant.SCHEDULE) {
                requests = routes.requests();
                schedule = routes.routes();
                long ptRoutes = schedule.stream().filter(route -> route.contains("[")).count();
                // the lines of pt-delays run in one direction only, so many of its requests have no pt route
                assertTrue(ptRoutes >= requests.size() / 10, "only " + ptRoutes + " of " + requests.size() + " routes use pt");
                continue;
            }
            assertEquals(requests, routes.requests());
            List<String> differences = new ArrayList<>();
            for (int i = 0; i < requests.size(); i++) {
                if (!schedule.get(i).equals(routes.routes().get(i))) {
                    differences.add(requests.get(i) + ": schedule " + schedule.get(i) + ", " + variant + " " + routes.routes().get(i));
                }
            }
            assertEquals(List.of(), differences.subList(0, Math.min(differences.size(), 10)),
                    differences.size() + " of " + requests.size() + " routes of " + variant + " differ from the schedule, the first ones");
        }
    }

    private record Routes(List<String> requests, List<String> routes) {
    }

    private static Routes route(Path configFile, Variant variant, int step) {
        Config config = ConfigUtils.loadConfig(configFile.toString());
        Scenario scenario = ScenarioUtils.loadScenario(config);
        SwissRailRaptor raptor = RaptorVariants.create(config, scenario, variant);
        TransitSchedule schedule = scenario.getTransitSchedule();

        double first = Double.POSITIVE_INFINITY;
        double last = Double.NEGATIVE_INFINITY;
        for (TransitLine line : schedule.getTransitLines().values()) {
            for (TransitRoute route : line.getRoutes().values()) {
                for (Departure departure : route.getDepartures().values()) {
                    first = Math.min(first, departure.getDepartureTime());
                    last = Math.max(last, departure.getDepartureTime());
                }
            }
        }

        List<String> requests = new ArrayList<>();
        List<String> routes = new ArrayList<>();
        for (TransitStopFacility from : schedule.getFacilities().values()) {
            for (TransitStopFacility to : schedule.getFacilities().values()) {
                if (from == to) {
                    continue;
                }
                for (double time = first - 600; time <= last; time += step) {
                    requests.add(from.getId() + " -> " + to.getId() + " at " + Time.writeTime(time));
                    routes.add(RaptorBenchmark.signature(raptor.calcRoute(DefaultRoutingRequest.of(from, to, time, null, new AttributesImpl()))));
                }
            }
        }
        return new Routes(requests, routes);
    }
}
