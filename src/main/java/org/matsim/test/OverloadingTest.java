package org.matsim.test;

import org.matsim.api.core.v01.Coord;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.TransportMode;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.api.core.v01.network.NetworkFactory;
import org.matsim.api.core.v01.network.Node;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.config.groups.QSimConfigGroup;
import org.matsim.core.config.groups.RoutingConfigGroup;
import org.matsim.core.config.groups.ScoringConfigGroup;
import org.matsim.core.controler.Controller;
import org.matsim.core.controler.ControllerUtils;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.network.NetworkUtils;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.vehicles.VehicleType;
import org.matsim.vehicles.VehicleUtils;
import org.matsim.vehicles.Vehicles;

public class OverloadingTest {
    public static void main(String[] args) {
        double sample = 0.01;
        double rate = 0.03;

        Config config = ConfigUtils.createConfig();
        config.qsim().setLinkDynamics(QSimConfigGroup.LinkDynamics.FIFO);
        config.controller().setOutputDirectory("./output/overloading-test-r" + rate + "-s" + sample);
        config.controller().setLastIteration(0);
        config.controller().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.deleteDirectoryIfExists);
        config.routing().setNetworkRouteConsistencyCheck(RoutingConfigGroup.NetworkRouteConsistencyCheck.disable);

        config.scoring().addActivityParams(new ScoringConfigGroup.ActivityParams("origin").setTypicalDuration(1.0));
        config.scoring().addActivityParams(new ScoringConfigGroup.ActivityParams("destination").setTypicalDuration(1.0));

        // TODO
//        config.qsim().setFlowCapFactor(0.01);
//        config.qsim().setStorageCapFactor(0.01);
        config.qsim().setTrafficDynamics(QSimConfigGroup.TrafficDynamics.queue);
        config.qsim().setStuckTime(30);
        config.qsim().setVehiclesSource(QSimConfigGroup.VehiclesSource.modeVehicleTypesFromVehiclesData);

        config.qsim().setFlowCapFactor(sample);
        config.qsim().setStorageCapFactor(sample);

        Network network = createNetwork();
        Population population = createPopulation(network, rate, rate);

        Scenario scenario = new ScenarioUtils.ScenarioBuilder(config)
                .setNetwork(network).setPopulation(population).build();

        Vehicles vehicles = scenario.getVehicles();
        vehicles.addVehicleType(VehicleUtils.createVehicleType(Id.create("car", VehicleType.class)));

        Controller controller = ControllerUtils.createController(scenario);
        controller.run();
    }

    //
    //              link1a             link1                                              link5
    //  (node1a) ----------> (node1) ------\                                            /-----> (node5)
    //             15m, 1800                \                                           /         150m, 1800
    //                                       v       link3              link4         /
    //                                  (intersection) ------> (node3) ------> (node4)
    //                                       ^           150m, 3600      150m, 3600
    //              link2a             link2 /
    //  (node2a) ----------> (node2) ------/
    //             15m, 3600   150m, 3600
    //
    static private Network createNetwork() {
        // Create network
        Network network = NetworkUtils.createNetwork();
        NetworkFactory factory = network.getFactory();

        // Nodes
        Node node1a = factory.createNode(Id.createNodeId("1a"), new Coord(-165, 75));
        Node node1 = factory.createNode(Id.createNodeId("1"), new Coord(-150, 75));
        Node node2a = factory.createNode(Id.createNodeId("2a"), new Coord(-165, -75));
        Node node2 = factory.createNode(Id.createNodeId("2"), new Coord(-150, -75));
        Node nodeIntersection = factory.createNode(Id.createNodeId("intersection"), new Coord(0, 0));
        Node node3 = factory.createNode(Id.createNodeId("3"), new Coord(150, 0));
        Node node4 = factory.createNode(Id.createNodeId("4"), new Coord(300, 0));
        Node node5 = factory.createNode(Id.createNodeId("5"), new Coord(450, 0));

        network.addNode(node1a);
        network.addNode(node1);
        network.addNode(node2a);
        network.addNode(node2);
        network.addNode(nodeIntersection);
        network.addNode(node3);
        network.addNode(node4);
        network.addNode(node5);

        // link1a: node1a -> node1, capacity 1800, length 15m
        Link link1a = factory.createLink(Id.createLinkId("1a"), node1a, node1);
        link1a.setLength(15.0);
        link1a.setCapacity(1800.0);
        link1a.setFreespeed(15.0);
        link1a.setNumberOfLanes(1);
        network.addLink(link1a);

        // link1: node1 -> intersection, capacity 1800, length 150m
        Link link1 = factory.createLink(Id.createLinkId("1"), node1, nodeIntersection);
        link1.setLength(150.0);
        link1.setCapacity(1800.0);
        link1.setFreespeed(15.0);
        link1.setNumberOfLanes(1);
        network.addLink(link1);

        // link2a: node2a -> node2, capacity 3600, length 15m
        Link link2a = factory.createLink(Id.createLinkId("2a"), node2a, node2);
        link2a.setLength(15.0);
        link2a.setCapacity(3600.0);
        link2a.setFreespeed(15.0);
        link2a.setNumberOfLanes(1);
        network.addLink(link2a);

        // link2: node2 -> intersection, capacity 3600, length 150m
        Link link2 = factory.createLink(Id.createLinkId("2"), node2, nodeIntersection);
        link2.setLength(150.0);
        link2.setCapacity(3600.0);
        link2.setFreespeed(15.0);
        link2.setNumberOfLanes(1);
        network.addLink(link2);

        // link3: intersection -> node3, capacity 3600, length 150m (out link)
        Link link3 = factory.createLink(Id.createLinkId("3"), nodeIntersection, node3);
        link3.setLength(150.0);
        link3.setCapacity(3600.0);
        link3.setFreespeed(15.0);
        link3.setNumberOfLanes(1);
        network.addLink(link3);

        // link4: node3 -> node4, capacity 3600, length 150m
        Link link4 = factory.createLink(Id.createLinkId("4"), node3, node4);
        link4.setLength(150.0);
        link4.setCapacity(3600.0);
        link4.setFreespeed(15.0);
        link4.setNumberOfLanes(1);
        network.addLink(link4);

        // link5: node4 -> node5, capacity 1800, length 150m
        Link link5 = factory.createLink(Id.createLinkId("5"), node4, node5);
        link5.setLength(150.0);
        link5.setCapacity(1800.0);
        link5.setFreespeed(15.0);
        link5.setNumberOfLanes(1);
        network.addLink(link5);

        return network;
    }

    static private Population createPopulation(Network network, double rateLink1, double rateLink2) {
        Population population = PopulationUtils.createPopulation(ConfigUtils.createConfig());
        PopulationFactory factory = population.getFactory();

        double startTime = 10 * 3600; // 10:00am
        double endTime = 11 * 3600;   // 11:00am
        double duration = endTime - startTime;

        int agentId = 0;

        // Agents departing on link1 -> link5
        int countLink1 = (int) (rateLink1 * duration);
        double intervalLink1 = 1.0 / rateLink1;
        for (int i = 0; i < countLink1; i++) {
            Person person = factory.createPerson(Id.createPersonId("link1_" + agentId++));
            Plan plan = factory.createPlan();

            Id<Link> linkId = Id.createLinkId("1a");
            Activity originActivity = factory.createActivityFromLinkId("origin", linkId);
            originActivity.setEndTime(startTime + i * intervalLink1);
            originActivity.setCoord(network.getLinks().get(linkId).getCoord());
            plan.addActivity(originActivity);

            plan.addLeg(factory.createLeg(TransportMode.car));

            Id<Link> linkId5 = Id.createLinkId("5");
            Activity destinationActivity = factory.createActivityFromLinkId("destination", linkId5);
            destinationActivity.setCoord(network.getLinks().get(linkId5).getCoord());
            plan.addActivity(destinationActivity);

            person.addPlan(plan);
            population.addPerson(person);
        }

        // Agents departing on link2a -> link5
        int countLink2 = (int) (rateLink2 * duration);
        double intervalLink2 = 1.0 / rateLink2;
        for (int i = 0; i < countLink2; i++) {
            Person person = factory.createPerson(Id.createPersonId("link2_" + agentId++));
            Plan plan = factory.createPlan();

            Id<Link> linkId = Id.createLinkId("2a");
            Activity originActivity = factory.createActivityFromLinkId("origin", linkId);
            originActivity.setEndTime(startTime + i * intervalLink2);
            originActivity.setCoord(network.getLinks().get(linkId).getCoord());
            plan.addActivity(originActivity);

            plan.addLeg(factory.createLeg(TransportMode.car));

            Id<Link> linkId5 = Id.createLinkId("5");
            Activity destinationActivity = factory.createActivityFromLinkId("destination", linkId5);
            destinationActivity.setCoord(network.getLinks().get(linkId5).getCoord());
            plan.addActivity(destinationActivity);

            person.addPlan(plan);
            population.addPerson(person);
        }

        return population;
    }
}
