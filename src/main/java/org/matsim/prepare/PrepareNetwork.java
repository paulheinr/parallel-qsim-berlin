package org.matsim.prepare;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.api.core.v01.network.Node;
import org.matsim.application.MATSimAppCommand;
import org.matsim.core.network.NetworkUtils;
import picocli.CommandLine;

import java.util.Set;

@CommandLine.Command(name = "prepare-network", description = "Prepares a MATSim network for simulation. I.e., adds one connection between PT and ")
public class PrepareNetwork implements MATSimAppCommand {
    private static final Logger log = LogManager.getLogger(PrepareNetwork.class);

    @CommandLine.Option(names = "--input", description = "Path to input network", required = true)
    private String input;

    public static void main(String[] args) {
        new PrepareNetwork().execute(args);
    }

    @Override
    public Integer call() throws Exception {
        Network network = NetworkUtils.readNetwork(input);

        network.getNodes().values().forEach(node -> {
            Set<Id<Link>> in = node.getInLinks().keySet();
            Set<Id<Link>> out = node.getOutLinks().keySet();
            if (isPt(in) != isPt(out)) {
                log.info("Node {} connects PT and non-PT links: \nIN: {}\nOUT: {}", node.getId(), in, out);
            }
        });

        // connect PT and car network at Gotzkowskybrücke
        Node from = network.getNodes().get(Id.createNodeId("pt_648553_bus"));
        Node to = network.getNodes().get(Id.createNodeId("cluster_1807917065_1929624603_1929624605_29962151_#3more"));

        NetworkUtils.createAndAddLink(network, Id.createLinkId("pt-connection"), from, to, 1, Double.MIN_VALUE, Double.MIN_VALUE, 1);
        NetworkUtils.writeNetwork(network, input.replace(".xml.gz", "-prepared.xml.gz"));

        return 0;
    }

    private boolean isPt(Set<Id<Link>> ids) {
        return ids.stream().anyMatch(id -> id.toString().startsWith("pt"));
    }
}
