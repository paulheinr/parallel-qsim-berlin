package org.matsim.test;

import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.population.Population;
import org.matsim.core.population.PopulationUtils;

public class CreateTestScenario {
    public static void main(String[] args) {
        Population population = PopulationUtils.readPopulation("/Users/paulh/public-svn/matsim/scenarios/countries/de/berlin/berlin-v6.4/input/berlin-v6.4-1pct.plans.xml.gz");
        population.getPersons().entrySet().removeIf(person -> !person.getKey().equals(Id.createPersonId("berlin_f7782e81")));
        PopulationUtils.writePopulation(population, "./output/test-scenario/test-population-berlin_f7782e81.xml.gz");
    }
}
