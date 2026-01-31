package org.matsim.test;

import org.apache.commons.lang3.tuple.Pair;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.events.LinkEnterEvent;
import org.matsim.api.core.v01.events.LinkLeaveEvent;
import org.matsim.api.core.v01.events.handler.LinkEnterEventHandler;
import org.matsim.api.core.v01.events.handler.LinkLeaveEventHandler;
import org.matsim.api.core.v01.network.Link;
import org.matsim.core.api.experimental.events.EventsManager;
import org.matsim.core.events.EventsUtils;
import org.matsim.vehicles.Vehicle;

import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;

public class OverloadingAnalysis {
    public static void main(String[] args) {

        double rate = 0.03;
        double sample = 0.01;

        String java = "./output/overloading-test-r" + rate + "-s" + sample;
        String rust = "./output/overloading_test-rust-r" + rate + "-s" + sample;

        {
            EventsManager eventsManager = EventsUtils.createEventsManager();
            LinkStats linkStats = new LinkStats();
            eventsManager.addHandler(linkStats);
            EventsUtils.readEvents(eventsManager, java + "/output_events.xml.gz");
            System.out.println(linkStats.travelTimes);
        }

        {
            LinkStats linkStats = new LinkStats();
            EventsManager rustEventsManager = EventsUtils.createEventsManager();
            rustEventsManager.addHandler(linkStats);
            EventsUtils.readEvents(rustEventsManager, rust + "/events.0.xml.gz");
            System.out.println(linkStats.travelTimes);
        }
    }

    static class LinkStats implements LinkLeaveEventHandler, LinkEnterEventHandler {
        private Map<Id<Link>, List<Double>> travelTimes = new HashMap<>();
        private Map<Pair<Id<Link>, Id<Vehicle>>, Double> enterTimes = new HashMap<>();

        @Override
        public void handleEvent(LinkEnterEvent event) {
            if (event.getLinkId().equals(Id.createLinkId("1a")) || event.getLinkId().equals(Id.createLinkId("2a"))) {
                return;
            }

            enterTimes.put(Pair.of(event.getLinkId(), event.getVehicleId()), event.getTime());
        }

        @Override
        public void handleEvent(LinkLeaveEvent event) {
            if (event.getLinkId().equals(Id.createLinkId("1a")) || event.getLinkId().equals(Id.createLinkId("2a"))) {
                return;
            }

            Double enter = enterTimes.remove(Pair.of(event.getLinkId(), event.getVehicleId()));
            travelTimes.putIfAbsent(event.getLinkId(), new LinkedList<>());
            travelTimes.get(event.getLinkId()).add(event.getTime() - enter);
        }
    }
}
