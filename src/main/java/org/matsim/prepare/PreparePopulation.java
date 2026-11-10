package org.matsim.prepare;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.population.*;
import org.matsim.application.MATSimAppCommand;
import org.matsim.application.prepare.population.CleanPopulation;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.router.TripStructureUtils;
import picocli.CommandLine;

import java.nio.file.Path;
import java.util.List;
import java.util.Set;

@CommandLine.Command(
        name = "prepare-population",
        description = "Filters the population by modes and removes unselected plans and routes.")
public class PreparePopulation implements MATSimAppCommand {
    public static final Logger log = LogManager.getLogger(PreparePopulation.class);
    public static final String PREPLANNING_HORIZON_ATTRIBUTE = "preplanningHorizon";

    @CommandLine.Option(names = "--input", description = "Path to population", required = true)
    private Path input;

    @CommandLine.Option(names = "--output", description = "Path of the filtered population. Default: the input path with -filtered before .xml")
    private Path output;

    @CommandLine.Option(names = "--modes", split = ",", description = "Positive set of modes that the selected plan is allowed to use. "
            + "Persons with other modes or with an activity without link are removed.")
    private Set<String> modes;

    @CommandLine.Option(names = "--exclude-routing-modes", split = ",", description = "Removes persons whose selected plan has a leg of one of these routing modes")
    private Set<String> excludeRoutingModes = Set.of();

    @CommandLine.Option(names = "--keep-unselected-plans", description = "Keep all plans instead of only the selected one")
    private boolean keepUnselectedPlans;

    @CommandLine.Option(names = "--remove-routes", description = "Remove the routes of all legs, so that they are routed again")
    private boolean removeRoutes;

    @Override
    public Integer call() {
        Population inputPopulation = PopulationUtils.readPopulation(input.toString());
        log.info("Read population with {} agents", inputPopulation.getPersons().size());

        if (modes != null) {
            log.info("Filtering population with the following modes: {}", modes);
            List<Id<Person>> filteredPersons = inputPopulation.getPersons().values().stream()
                    .map(HasPlansAndId::getSelectedPlan)
                    .filter(p -> TripStructureUtils.getLegs(p).stream().anyMatch(l -> !modes.contains(l.getMode())) || !allActivityLinksSet(p))
                    .map(p -> p.getPerson().getId()).toList();
            log.info("Removing {} agents from population", filteredPersons.size());
            filteredPersons.forEach(inputPopulation::removePerson);
        }

        if (!excludeRoutingModes.isEmpty()) {
            List<Id<Person>> excludedPersons = inputPopulation.getPersons().values().stream()
                    .filter(p -> TripStructureUtils.getLegs(p.getSelectedPlan()).stream()
                            .anyMatch(l -> excludeRoutingModes.contains(l.getRoutingMode())))
                    .map(Person::getId).toList();
            log.info("Removing {} agents with a leg of routing mode {} in the selected plan", excludedPersons.size(), excludeRoutingModes);
            excludedPersons.forEach(inputPopulation::removePerson);
        }

        for (Person person : inputPopulation.getPersons().values()) {
            if (!keepUnselectedPlans) {
                CleanPopulation.removeUnselectedPlans(person);
            }
            if (removeRoutes) {
                person.getPlans().forEach(plan -> plan.getPlanElements().forEach(CleanPopulation::removeRouteFromLeg));
            }
        }

        log.info("Filtered population contains {} agents", inputPopulation.getPersons().size());

        String outputPath = output != null ? output.toString() : input.toString().replace(".xml", "-filtered" + ".xml");
        log.info("Writing filtered population to {}", outputPath);

        PopulationUtils.writePopulation(inputPopulation, outputPath);

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
}
