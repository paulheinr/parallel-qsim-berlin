package org.matsim.routing;

import ch.sbb.matsim.config.SwissRailRaptorConfigGroup;
import ch.sbb.matsim.routing.pt.raptor.*;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Scenario;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.pt.transitSchedule.api.TransitLine;
import org.matsim.pt.transitSchedule.api.TransitRoute;
import org.matsim.pt.transitSchedule.api.TransitRouteStop;
import org.matsim.pt.transitSchedule.api.TransitSchedule;
import org.matsim.routing.TimetableMessages.SnapshotZero;
import org.matsim.schemas.services.routing.v1.TimetableUpdate;

import java.util.ArrayList;
import java.util.List;

/**
 * The variants of SwissRailRaptor that are compared by {@link RaptorBenchmark} and {@link RaptorVariantsTest}.
 * <p>
 * Only {@link Variant#SCHEDULE} also runs with the matsim jar from before the timetable updates. The other variants
 * use classes and methods that exist only since then; they are in {@link Updates}, which only these variants load.
 */
final class RaptorVariants {
    private static final Logger log = LogManager.getLogger(RaptorVariants.class);

    enum Variant {
        /**
         * The default: the times of the transit schedule, without {@code useTimetableUpdates}.
         */
        SCHEDULE,
        /**
         * With {@code useTimetableUpdates}, still on the times of the transit schedule: shows the effect of the
         * transfer filters that the option changes.
         */
        OPTION,
        /**
         * With {@code useTimetableUpdates}, on snapshot 0 as a {@link VersionedRaptorTimetable}: built by
         * {@link TimetableVersions} from the {@code BaseRoute} messages, as the router builds it from the messages of
         * Rust.
         */
        VERSIONED
    }

    private RaptorVariants() {
    }

    /**
     * Removes the routes of {@code schedule} that arrive at a stop before they depart from the previous one. These are
     * errors in the data (8 bus routes with 31 departures in Berlin v7.1), which the default raptor accepts and
     * {@link VersionedRaptorTimetable} rejects. The benchmarks remove them for all variants, so that all route on the
     * same schedule.
     *
     * @return the number of removed routes
     */
    static int removeRoutesRunningBackwards(TransitSchedule schedule) {
        List<TransitRoute> removed = new ArrayList<>();
        int departures = 0;
        for (TransitLine line : schedule.getTransitLines().values()) {
            for (TransitRoute route : List.copyOf(line.getRoutes().values())) {
                List<TransitRouteStop> stops = route.getStops();
                for (int i = 1; i < stops.size(); i++) {
                    double arrival = stops.get(i).getArrivalOffset().or(stops.get(i)::getDepartureOffset).seconds();
                    double previousDeparture = stops.get(i - 1).getDepartureOffset().or(stops.get(i - 1)::getArrivalOffset).seconds();
                    if (arrival < previousDeparture) {
                        line.removeRoute(route);
                        removed.add(route);
                        departures += route.getDepartures().size();
                        break;
                    }
                }
            }
        }
        log.info("Removed {} transit routes with {} departures that arrive at a stop before they depart from the previous one: {}",
                removed.size(), departures, removed.stream().map(route -> route.getId().toString()).toList());
        return removed.size();
    }

    /**
     * @param config the config of {@code scenario}. For {@link Variant#OPTION} and {@link Variant#VERSIONED}, this sets
     *               {@code useTimetableUpdates} in it.
     */
    static SwissRailRaptor create(Config config, Scenario scenario, Variant variant) {
        if (variant == Variant.SCHEDULE) {
            return new SwissRailRaptor.Builder(data(config, scenario), config).build();
        }
        return Updates.create(config, scenario, variant == Variant.VERSIONED);
    }

    private static SwissRailRaptorData data(Config config, Scenario scenario) {
        return SwissRailRaptorData.create(scenario.getTransitSchedule(), scenario.getTransitVehicles(), RaptorUtils.createStaticConfig(config),
                scenario.getNetwork(), null);
    }

    /**
     * The variants with {@code useTimetableUpdates}.
     */
    private static final class Updates {

        static SwissRailRaptor create(Config config, Scenario scenario, boolean versioned) {
            ConfigUtils.addOrGetModule(config, SwissRailRaptorConfigGroup.class).setUseTimetableUpdates(true);
            SwissRailRaptorData data = data(config, scenario);
            SwissRailRaptor.Builder builder = new SwissRailRaptor.Builder(data, config);
            if (versioned) {
                VersionedRaptorTimetable snapshotZero = snapshotZero(data, scenario);
                builder.with((routeData, departureTime, person, routingAttributes) -> snapshotZero);
            }
            return builder.build();
        }

        /**
         * Snapshot 0 of the schedule of {@code scenario}, built by {@link TimetableVersions} as in the router.
         */
        private static VersionedRaptorTimetable snapshotZero(SwissRailRaptorData data, Scenario scenario) {
            TimetableVersions versions = new TimetableVersions(data);
            for (TimetableUpdate message : new SnapshotZero(scenario.getTransitSchedule()).messages()) {
                versions.addBaseRoute(message.getBaseRoute());
            }
            versions.startIteration(0);
            return versions.get(0, 0).join();
        }
    }
}
