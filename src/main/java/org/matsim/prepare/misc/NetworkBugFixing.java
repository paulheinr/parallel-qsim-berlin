package org.matsim.prepare.misc;

import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.core.network.NetworkUtils;

public class NetworkBugFixing {
    public static void main(String[] args) {
        Network network = NetworkUtils.readNetwork("output/v6.4/berlin-v6.4-10pct.network.12.xml.gz");

        Link link = network.getLinks().get(Id.createLinkId("431573846#0"));

        System.out.println("=== LINK ===");
        System.out.println(link);
        System.out.println(link.getAttributes());

        System.out.println("=== FROM NODE ===");
        System.out.println(link.getFromNode());
        System.out.println(link.getFromNode().getAttributes());

        System.out.println("=== TO NODE ===");
        System.out.println(link.getToNode());
        System.out.println(link.getToNode().getAttributes());

        System.out.println("=== FROM LINK ===");
        System.out.println(network.getLinks().get(Id.createLinkId("-19875855#0")).getAttributes());

        System.out.println("=== TO LINK ===");
        System.out.println(network.getLinks().get(Id.createLinkId("993314009")).getAttributes());

//        Population population = PopulationUtils.readPopulation("output/v6.4/berlin-v6.4-10pct.plans-filtered.xml.gz");
//        List<Id<Person>> list = population.getPersons().keySet().stream().filter(id -> !id.equals(Id.createPersonId("goodsTraffic_re_vkz.0693_4_41"))).toList();
//        for (Id<Person> personId : list) {
//            population.removePerson(personId);
//        }
//        PopulationUtils.writePopulation(population, "output/v6.4/berlin-bug-fix.xml.gz");
    }
}
