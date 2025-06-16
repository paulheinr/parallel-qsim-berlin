package org.matsim.prepare.misc;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.core.network.NetworkUtils;

public class NetworkBugFixing {
    private static final Logger log = LogManager.getLogger(NetworkBugFixing.class);

    public static void main(String[] args) {
        Network network = NetworkUtils.readNetwork("output/v6.4/berlin-v6.4-10pct.network.12.xml.gz");

        Link link = network.getLinks().get(Id.createLinkId("431573846#0"));

        log.info("=== LINK ===");
        log.info("{}", link);
        log.info("{}", link.getAttributes());

        log.info("=== FROM NODE ===");
        log.info("{}", link.getFromNode());
        log.info("{}", link.getFromNode().getAttributes());

        log.info("=== TO NODE ===");
        log.info("{}", link.getToNode());
        log.info("{}", link.getToNode().getAttributes());

        log.info("=== FROM LINK ===");
        log.info("{}", network.getLinks().get(Id.createLinkId("-19875855#0")).getAttributes());

        log.info("=== TO LINK ===");
        log.info("{}", network.getLinks().get(Id.createLinkId("993314009")).getAttributes());

//        Population population = PopulationUtils.readPopulation("output/v6.4/berlin-v6.4-10pct.plans-filtered.xml.gz");
//        List<Id<Person>> list = population.getPersons().keySet().stream().filter(id -> !id.equals(Id.createPersonId("goodsTraffic_re_vkz.0693_4_41"))).toList();
//        for (Id<Person> personId : list) {
//            population.removePerson(personId);
//        }
//        PopulationUtils.writePopulation(population, "output/v6.4/berlin-bug-fix.xml.gz");
    }
}
