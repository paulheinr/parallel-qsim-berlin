package org.matsim.analysis;

import org.matsim.api.core.v01.population.Activity;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Plan;
import org.matsim.api.core.v01.population.Population;
import org.matsim.application.MATSimAppCommand;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.router.TripStructureUtils;
import picocli.CommandLine;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

//Purpose: Analyze the activity data and investigate the preplanning horizon.
//Questions to answer:
//        - How many activities are there in the input plans whose duration is zero but there is a non-zero preplanning horizon?
//        - Does this differ compared to the output plans? (-> Need to write some other scripts for that to extract the data from the protobuf output)
public class ActivityAnalysis implements MATSimAppCommand {
    @CommandLine.Option(names = "--plansFile", description = "Path to plans file")
    private String plansFile = "https://svn.vsp.tu-berlin.de/repos/public-svn/matsim/scenarios/countries/de/dresden/dresden-v1.0/input/dresden-v1.0-10pct.plans-initial.xml.gz";
    //"output/v6.4/10pct/berlin-v6.4-10pct.plans-filtered_600.xml.gz";

    public static void main(String[] args) {
        new ActivityAnalysis().execute(args);
    }

    @Override
    public Integer call() throws Exception {
        Population population = PopulationUtils.readPopulation(plansFile);

        int actCount = 0;
        int act0Count = 0;

        // filter activities with smaller duration than 600
        for (Person person : population.getPersons().values()) {
            Plan p = person.getSelectedPlan();
            List<Activity> activities = PopulationUtils.getActivities(p, TripStructureUtils.StageActivityHandling.ExcludeStageActivities);
            int counter = 0;
            for (Activity activity : activities) {
                AtomicBoolean is0 = new AtomicBoolean(false);
                activity.getMaximumDuration().ifDefined(duration -> {
                    if (duration <= 0.) {
                        is0.set(true);
                    }
                });
                if (is0.get()) {
                    act0Count++;
                }
                actCount++;
                counter++;
            }
        }

        // Print summary
        System.out.println("Total activities: " + actCount);
        System.out.println("Activities with zero duration: " + act0Count);

        return 0;
    }
}
