package org.matsim.analysis;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.jetbrains.annotations.NotNull;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.population.Person;
import org.matsim.application.MATSimAppCommand;
import org.matsim.core.api.experimental.events.EventsManager;
import org.matsim.core.api.experimental.events.TeleportationArrivalEvent;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.events.MatsimEventsReader;
import org.matsim.core.network.NetworkUtils;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.scoring.EventsToActivities;
import org.matsim.core.scoring.EventsToLegs;
import org.matsim.core.scoring.ExperiencedPlansService;
import org.matsim.core.scoring.ExperiencedPlansServiceFactory;
import org.matsim.pt.transitSchedule.api.TransitScheduleReader;
import picocli.CommandLine;

import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.Queue;

public class ExperiencedPlansWriter implements MATSimAppCommand {
    private static final Logger log = LogManager.getLogger(ExperiencedPlansWriter.class);

    @CommandLine.Option(names = "--network", description = "Path to network")
    private String network = "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/berlin-v6.4-network-with-pt-prepared.xml.gz";

    @CommandLine.Option(names = "--population", description = "Path to population")
    private String population = "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/berlin-v6.4-1pct.plans-filtered.xml.gz";

    @CommandLine.Option(names = "--transit-schedule", description = "Path to transit schedule")
    private String transitSchedule = "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/berlin-v6.4-transitSchedule.xml.gz";

    @CommandLine.Option(names = "--events", description = "Path to events file")
    private Path eventsFile = Path.of("/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/output/events.xml.gz");

    @CommandLine.Option(names = "--output", description = "Path to output experienced plans file")
    private String output = "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/output/experiencedPlans.xml.gz";

    public static void main(String[] args) {
        new ExperiencedPlansWriter().execute(args);
    }

    @Override
    public Integer call() throws Exception {
        Config config = ConfigUtils.createConfig();
        config.eventsManager().setNumberOfThreads(1);

        EventsManager eventsManager = EventsUtils.createEventsManager(config);

        Scenario scenario = new ScenarioUtils.ScenarioBuilder(config)
                .setNetwork(NetworkUtils.readNetwork(network))
                .setPopulation(PopulationUtils.readPopulation(population))
                .build();
        new TransitScheduleReader(scenario).readFile(transitSchedule);

        EventsToActivities eventsToActivities = new EventsToActivities();
        EventsToLegs eventsToLegs = new EventsToLegs(scenario);

        Map<Id<Person>, Queue<TravelledWithPt>> ptCache = new HashMap<>();

        eventsToLegs.addLegHandler(leg -> {
            // add additional information about teleported pt legs from the cached events
            if (!leg.getLeg().getMode().equals("pt")) {
                return;
            }

            TravelledWithPt event = ptCache.get(leg.getAgentId()).poll();

            if (event == null) {
                throw new RuntimeException("No travelled with pt event found for person " + leg.getAgentId());
            }

            leg.getLeg().getAttributes().putAttribute("route", event.route);
            leg.getLeg().getAttributes().putAttribute("line", event.line);
        });

        eventsManager.addHandler(eventsToActivities);
        eventsManager.addHandler(eventsToLegs);

        ExperiencedPlansService experiencedPlansService = ExperiencedPlansServiceFactory.create(scenario, eventsToActivities, eventsToLegs);

//        String output = eventsFile.getParent().resolve("experiencedPlans.xml.gz").toString();

        log.info("Reading events from file: {}", eventsFile);
        eventsManager.initProcessing();

        MatsimEventsReader matsimEventsReader = getMatsimEventsReader(eventsManager, ptCache);
        matsimEventsReader.readFile(eventsFile.toString());

        eventsManager.finishProcessing();

        // I just put in the following manually.  It is normally called from a mobsim listener.  There might be a better place to do this but took me
        // already 2 hrs to get to this point here. kai, nov'25
        eventsToActivities.finish();

        log.info("Writing experienced plans to file: {}", output);
        experiencedPlansService.writeExperiencedPlans(output);

        return 0;
    }

    @NotNull
    private static MatsimEventsReader getMatsimEventsReader(EventsManager eventsManager, Map<Id<Person>, Queue<TravelledWithPt>> ptCache) {
        MatsimEventsReader matsimEventsReader = new MatsimEventsReader(eventsManager);
        // convert special teleported pt events to normal teleportation events and cache the additional info for later use‚
        matsimEventsReader.addCustomEventMapper("travelled with pt", event -> {
            String person = event.getAttributes().get("person");
            String distance = event.getAttributes().get("distance");
            String mode = event.getAttributes().get("mode");
            String line = event.getAttributes().get("line");
            String route = event.getAttributes().get("route");

            ptCache.computeIfAbsent(Id.createPersonId(person), k -> new java.util.concurrent.ConcurrentLinkedQueue<>())
                    .add(new TravelledWithPt(event.getTime(), Id.createPersonId(person), Double.parseDouble(distance), mode, line, route));

            return new TeleportationArrivalEvent(event.getTime(), Id.createPersonId(person), Double.parseDouble(distance), mode);
        });
        return matsimEventsReader;
    }

    record TravelledWithPt(double time, Id<Person> person, double distance, String mode, String line, String route) {
    }
}
