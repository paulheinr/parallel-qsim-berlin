package org.matsim.analysis;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVPrinter;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.population.Activity;
import org.matsim.api.core.v01.population.Leg;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Population;
import org.matsim.application.MATSimAppCommand;
import org.matsim.core.population.PopulationUtils;
import picocli.CommandLine;

import java.io.FileWriter;
import java.io.IOException;
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

        List<LegEntry> baseLegs = new LinkedList<>();
        List<LegEntry> rustLegs = new LinkedList<>();
        List<ActivityEntry> baseActs = new LinkedList<>();
        List<ActivityEntry> rustActs = new LinkedList<>();

        fillEntries(population, baseLegs, baseActs);
        fillEntries(rustPopulation, rustLegs, rustActs);

        writeLegCsv(baseLegs, "base_");
        writeLegCsv(rustLegs, "rust_");
        writeActivityCsv(baseActs, "base_");
        writeActivityCsv(rustActs, "rust_");

        return 0;
    }

    private void writeLegCsv(List<LegEntry> baseLegs, String prefix) throws IOException {
        try (CSVPrinter legsPrinter = new CSVPrinter(
                new FileWriter(output + prefix + "legs.csv"),
                CSVFormat.DEFAULT.builder()
                        .setHeader("personId", "index", "mode", "routingMode", "startTime", "baseTravelTime")
                        .build())) {

            for (LegEntry baseLeg : baseLegs) {
                legsPrinter.printRecord(
                        baseLeg.personId().toString(),
                        baseLeg.elementIndex(),
                        baseLeg.mode(),
                        baseLeg.routingMode(),
                        baseLeg.startTime(),
                        baseLeg.travelTime()
                );
            }
        }
    }

    private void writeActivityCsv(List<ActivityEntry> baseActs, String prefix) throws IOException {
        try (CSVPrinter actsPrinter = new CSVPrinter(
                new FileWriter(output + prefix + "activities.csv"),
                CSVFormat.DEFAULT.builder()
                        .setHeader("personId", "index", "type", "maxDur", "startTime", "endTime")
                        .build())) {

            for (ActivityEntry baseAct : baseActs) {
                actsPrinter.printRecord(
                        baseAct.personId().toString(),
                        baseAct.elementIndex(),
                        baseAct.type(),
                        baseAct.max_dur(),
                        baseAct.start(),
                        baseAct.end()
                );
            }
        }
    }

    private static void fillEntries(Population population, List<LegEntry> baseLegs, List<ActivityEntry> baseActs) {
        for (Person person : population.getPersons().values()) {
            for (int i = 0; i < person.getSelectedPlan().getPlanElements().size(); i++) {
                if (person.getSelectedPlan().getPlanElements().get(i) instanceof Leg leg) {
                    var entry = new LegEntry(i, person.getId(), leg.getMode(), leg.getRoutingMode(),
                            leg.getDepartureTime().seconds(), leg.getTravelTime().seconds());
                    baseLegs.add(entry);
                } else if (person.getSelectedPlan().getPlanElements().get(i) instanceof Activity activity) {
                    var entry = new ActivityEntry(i, person.getId(), activity.getType(),
                            activity.getMaximumDuration().orElse(Double.NaN),
                            activity.getStartTime().orElse(Double.NaN),
                            activity.getEndTime().orElse(Double.NaN));
                    baseActs.add(entry);
                }
            }
        }
    }

    record LegEntry(int elementIndex, Id<Person> personId, String mode, String routingMode, double startTime,
                    double travelTime) {
    }

    record ActivityEntry(int elementIndex, Id<Person> personId, String type, double max_dur, double start, double end) {
    }
}
