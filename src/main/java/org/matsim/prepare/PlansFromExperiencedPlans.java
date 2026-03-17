package org.matsim.prepare;

import org.matsim.api.core.v01.population.Activity;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Plan;
import org.matsim.api.core.v01.population.Population;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.router.TripStructureUtils;

import java.util.List;

import static org.matsim.prepare.PreparePopulation.PREPLANNING_HORIZON_ATTRIBUTE;

public class PlansFromExperiencedPlans {
    public static void main(String[] args) {
        Population inputPop = PopulationUtils.readPopulation("/Users/paulh/public-svn/matsim/scenarios/countries/de/berlin/berlin-v6.4/output/berlin-v6.4-10pct/berlin-v6.4.output_experienced_plans.xml.gz");

        for (Person person : inputPop.getPersons().values()) {
            Plan selectedPlan = person.getSelectedPlan();
            List<Activity> acts = TripStructureUtils.getActivities(selectedPlan, TripStructureUtils.StageActivityHandling.StagesAsNormalActivities);
            int count = 0;
            int last = acts.size();
            for (Activity act : acts) {
                count++;

                if (count == 1 || count == last) {
                    //skip first / last activity
                    continue;
                }

                if (act.getType().contains("interaction")) {
                    act.setMaximumDuration(0);
                } else {
                    double dur = act.getEndTime().orElseThrow(() -> new RuntimeException("No end time in act " + act + "defined")) -
                            act.getStartTime().orElseThrow(() -> new RuntimeException("No start time in act " + act + "defined"));
                    act.setMaximumDuration(dur);
                }
                act.setEndTimeUndefined();
                act.setStartTimeUndefined();
            }

            TripStructureUtils.getTrips(selectedPlan).stream()
                    .filter(t -> TripStructureUtils.identifyMainMode(t.getTripElements()).equals("pt"))
                    .forEach(t -> t.getOriginActivity().getAttributes().putAttribute(PREPLANNING_HORIZON_ATTRIBUTE, 600));
        }

        PopulationUtils.writePopulation(inputPop, "/Users/paulh/git/parallel-qsim-berlin/output/plans-10pct-from-experienced.xml.gz");
    }
}
