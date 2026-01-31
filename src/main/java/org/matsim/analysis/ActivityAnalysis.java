package org.matsim.analysis;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVPrinter;
import org.apache.commons.lang3.tuple.Pair;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.population.*;
import org.matsim.application.MATSimAppCommand;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.router.TripStructureUtils;
import picocli.CommandLine;

import java.io.FileWriter;
import java.util.LinkedList;
import java.util.List;

public class ActivityAnalysis implements MATSimAppCommand {
    @CommandLine.Option(names = "--base", description = "Path to plans file")
    private String basePlans = "/Users/paulh/git/matsim-berlin/output/berlin-v6.4-1pct/berlin-v6.4.output_experienced_plans.xml.gz";

    @CommandLine.Option(names = "--rust")
    private String rustPlans = "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/output-16/experiencedPlans.xml.gz";

    @CommandLine.Option(names = "--output")
    private String output = "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/output-16/";

    public static void main(String[] args) {
        new ActivityAnalysis().execute(args);
    }

    @Override
    public Integer call() throws Exception {
        Population population = PopulationUtils.readPopulation(basePlans);
        Population rustPopulation = PopulationUtils.readPopulation(rustPlans);

        if (population.getPersons().size() - 6 != rustPopulation.getPersons().size()) {
            throw new RuntimeException("Number of persons does not match number of rust plans.");
        }

        List<Pair<LegEntry, LegEntry>> legs = new LinkedList<>();
        List<Pair<ActivityEntry, ActivityEntry>> acts = new LinkedList<>();

        for (Person person : population.getPersons().values()) {
            if (person.getId().equals(Id.createPersonId("berlin_f7782e81"))) {
                // skip because this person is stuck
                continue;
            }

            Person rustPerson = rustPopulation.getPersons().get(person.getId());
            if (rustPerson == null) {
                continue;
            }

            Plan rustPlan = rustPerson.getSelectedPlan();
            Plan basePlan = person.getSelectedPlan();
            if (rustPlan.getPlanElements().size() != basePlan.getPlanElements().size()) {
                throw new RuntimeException("Number of plan elements does not match for person " + person.getId());
            }
            List<Leg> baseLegs = TripStructureUtils.getLegs(basePlan);
            List<Leg> rustLegs = TripStructureUtils.getLegs(rustPlan);

            for (int i = 0; i < baseLegs.size(); i++) {
                Leg baseLeg = baseLegs.get(i);
                Leg rustLeg = rustLegs.get(i);
                if (!baseLeg.getMode().equals(rustLeg.getMode())) {
                    throw new RuntimeException("Leg mode does not match for person " + person.getId() + " at leg " + i);
                }
                if (!baseLeg.getRoutingMode().equals(rustLeg.getRoutingMode())) {
                    throw new RuntimeException("Leg routing mode does not match for person " + person.getId() + " at leg " + i);
                }
                var baseLegEntry = new LegEntry(person.getId(), baseLeg.getMode(), baseLeg.getRoutingMode(),
                        baseLeg.getDepartureTime().seconds(), baseLeg.getTravelTime().seconds());
                var rustLegEntry = new LegEntry(person.getId(), rustLeg.getMode(), rustLeg.getRoutingMode(),
                        rustLeg.getDepartureTime().seconds(), rustLeg.getTravelTime().seconds());
                legs.add(Pair.of(baseLegEntry, rustLegEntry));
            }

            List<Activity> activities = TripStructureUtils.getActivities(basePlan, TripStructureUtils.StageActivityHandling.StagesAsNormalActivities);
            List<Activity> rustActivities = TripStructureUtils.getActivities(rustPlan, TripStructureUtils.StageActivityHandling.StagesAsNormalActivities);

            for (int i = 0; i < activities.size(); i++) {
                Activity baseAct = activities.get(i);
                Activity rustAct = rustActivities.get(i);
                var baseActEntry = new ActivityEntry(person.getId(), baseAct.getType(), baseAct.getMaximumDuration().orElse(Double.NaN),
                        baseAct.getStartTime().orElse(Double.NaN), baseAct.getEndTime().orElse(Double.NaN));
                var rustActEntry = new ActivityEntry(person.getId(), rustAct.getType(), rustAct.getMaximumDuration().orElse(Double.NaN),
                        rustAct.getStartTime().orElse(Double.NaN), rustAct.getEndTime().orElse(Double.NaN));
                acts.add(Pair.of(baseActEntry, rustActEntry));
            }
        }

        // write 2 csv files:
        // 1) legs csv, header: personId, baseMode, baseRoutingMode, baseStartTime, baseTravelTime, rustMode, rustRoutingMode, rustStartTime, rustTravelTime
        try (CSVPrinter legsPrinter = new CSVPrinter(
                new FileWriter(output + "legs.csv"),
                CSVFormat.DEFAULT.builder()
                        .setHeader("personId", "baseMode", "baseRoutingMode", "baseStartTime", "baseTravelTime",
                                "rustMode", "rustRoutingMode", "rustStartTime", "rustTravelTime")
                        .build())) {

            for (Pair<LegEntry, LegEntry> entry : legs) {
                var base = entry.getLeft();
                var rust = entry.getRight();

                legsPrinter.printRecord(
                        base.personId().toString(),
                        base.mode(),
                        base.routingMode(),
                        base.startTime(),
                        base.travelTime(),
                        rust.mode(),
                        rust.routingMode(),
                        rust.startTime(),
                        rust.travelTime()
                );
            }
        }

        // 2) activities csv, header: personId, baseType, baseMaxDur, baseStart, baseEnd, rustType, rustMaxDur, rustStart, rustEnd
        try (CSVPrinter activitiesPrinter = new CSVPrinter(
                new FileWriter(output + "activities.csv"),
                CSVFormat.DEFAULT.builder()
                        .setHeader("personId", "baseType", "baseMaxDur", "baseStart", "baseEnd",
                                "rustType", "rustMaxDur", "rustStart", "rustEnd")
                        .build())) {

            for (Pair<ActivityEntry, ActivityEntry> entry : acts) {
                var base = entry.getLeft();
                var rust = entry.getRight();

                activitiesPrinter.printRecord(
                        base.personId().toString(),
                        base.type(),
                        base.max_dur(),
                        base.start(),
                        base.end(),
                        rust.type(),
                        rust.max_dur(),
                        rust.start(),
                        rust.end()
                );
            }
        }

        return 0;
    }

    record LegEntry(Id<Person> personId, String mode, String routingMode, double startTime, double travelTime) {
    }

    record ActivityEntry(Id<Person> personId, String type, double max_dur, double start, double end) {
    }
}
