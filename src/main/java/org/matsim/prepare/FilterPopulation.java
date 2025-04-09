package org.matsim.prepare;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.TransportMode;
import org.matsim.api.core.v01.population.*;
import org.matsim.application.MATSimAppCommand;
import org.matsim.application.prepare.population.CleanPopulation;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.population.routes.NetworkRoute;
import org.matsim.core.population.routes.RouteUtils;
import org.matsim.core.router.TripStructureUtils;
import picocli.CommandLine;

import java.nio.file.Path;
import java.util.List;
import java.util.Set;

@CommandLine.Command(
        name = "filter-population",
        description = "Filters population by a given set of modes. Preserves all agents using only these modes.")
public class FilterPopulation implements MATSimAppCommand {
    public static final Logger log = LogManager.getLogger(FilterPopulation.class);

    @CommandLine.Option(names = "--input", description = "Path to population", required = true)
    private Path input;

    @CommandLine.Option(names = "--modes", split = ",", description = "Positive set of modes that the population is allowed to use")
    private Set<String> modes;

    @Override
    public Integer call() throws Exception {
        Population inputPopulation = PopulationUtils.readPopulation(input.toString());
        log.info("Read population with {} agents", inputPopulation.getPersons().size());
        log.info("Filtering population with the following modes: {}", modes);

        List<Id<Person>> filteredPersons = inputPopulation.getPersons().values().stream()
                .map(p -> p.getSelectedPlan())
                .filter(p -> TripStructureUtils.getLegs(p).stream().anyMatch(l -> !modes.contains(l.getMode())) || !allActivityLinksSet(p))
                .map(p -> p.getPerson().getId()).toList();

        log.info("Removing {} agents from population", filteredPersons.size());

        for (Id<Person> id : filteredPersons) {
            inputPopulation.removePerson(id);
        }

        for (Person person : inputPopulation.getPersons().values()) {
            CleanPopulation.removeUnselectedPlans(person);

            // This is necessary because the rust QSim implicitly assumes generic routes for teleportation.
            // See https://github.com/matsim-vsp/parallel_qsim_rust/issues/149
            replaceLinksRoutes(person, Set.of(TransportMode.ride, TransportMode.bike));
        }

        log.info("Filtered population contains {} agents", inputPopulation.getPersons().size());

        String output = input.toString().replace(".xml", "-filtered.xml");
        log.info("Writing filtered population to {}", output);

        PopulationUtils.writePopulation(inputPopulation, output);

        return 0;
    }

    private static boolean allActivityLinksSet(Plan plan) {
        for (Activity act : TripStructureUtils.getActivities(plan, TripStructureUtils.StageActivityHandling.StagesAsNormalActivities)) {
            if (act.getLinkId() == null) {
                log.warn("Person {} has activities with no link id.", plan.getPerson().getId());
                return false;
            }
        }
        return true;
    }

    /**
     * Replaces all routes of given modes with generic routes.
     */
    private static void replaceLinksRoutes(Person person, Set<String> modes) {
        Plan plan = person.getSelectedPlan();
        for (Leg leg : TripStructureUtils.getLegs(plan)) {
            if (!modes.contains(leg.getMode())) {
                continue;
            }

            if (leg.getRoute() instanceof NetworkRoute) {
                leg.setRoute(convertLinksRouteToGenericRoute(leg.getRoute()));
            }
        }
    }

    private static Route convertLinksRouteToGenericRoute(Route route) {
        if (!(route instanceof NetworkRoute)) {
            throw new IllegalArgumentException("Route is not a NetworkRoute");
        }

        Route genericRouteImpl = RouteUtils.createGenericRouteImpl(route.getStartLinkId(), route.getEndLinkId());
        genericRouteImpl.setDistance(route.getDistance());
        genericRouteImpl.setTravelTime(route.getTravelTime().orElseThrow(() -> new IllegalStateException("Travel time not set")));

        return genericRouteImpl;
    }
}
