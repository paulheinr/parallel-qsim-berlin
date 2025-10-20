package org.matsim.routing;

import com.google.inject.Key;
import com.google.inject.name.Names;
import com.google.protobuf.Empty;
import io.grpc.stub.StreamObserver;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.jetbrains.annotations.NotNull;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.Activity;
import org.matsim.api.core.v01.population.Leg;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.PlanElement;
import org.matsim.core.config.Config;
import org.matsim.core.controler.ControllerUtils;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.population.routes.NetworkRoute;
import org.matsim.core.router.LinkWrapperFacility;
import org.matsim.core.router.RoutingModule;
import org.matsim.core.router.RoutingRequest;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.facilities.Facility;
import org.matsim.pt.routes.DefaultTransitPassengerRoute;
import org.matsim.utils.objectattributes.attributable.Attributes;
import routing.Routing;
import routing.RoutingServiceGrpc;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class RoutingService extends RoutingServiceGrpc.RoutingServiceImplBase {
    private static final Logger log = LogManager.getLogger(RoutingService.class);
    private final ThreadLocal<RoutingModule> swissRailRaptor;
    private final ThreadLocal<Scenario> scenario;
    private final Runnable shutdown;
    private final Config config;
    private Map<String, Integer> threadNums = new HashMap<>();
    private final ConcurrentMap<Integer, List<ProfilingEntry>> profilingEntries = new ConcurrentHashMap<>(10);

    private RoutingService(ThreadLocal<RoutingModule> raptorThreadLocal, ThreadLocal<Scenario> scenarioThreadLocal, Runnable shutdown, Config config) {
        this.swissRailRaptor = raptorThreadLocal;
        this.scenario = scenarioThreadLocal;
        this.shutdown = shutdown;
        this.config = config;
    }

    /**
     * Initializes the service by loading the Swiss Rail Raptor and scenario.
     * This method should be called before any routing requests are processed.
     */
    public void init() {
        this.swissRailRaptor.get();
        this.scenario.get();
    }

    @Override
    public void shutdown(Empty request, StreamObserver<Empty> responseObserver) {
        log.info("Received shutdown request");
        writeProfilingEntries();

        log.info("Shutting down routing service");
        responseObserver.onNext(Empty.getDefaultInstance());
        responseObserver.onCompleted();
        new Thread(shutdown).start();
    }

    @Override
    public void getRoute(Routing.Request request, StreamObserver<Routing.Response> responseObserver) {
        long startTime = System.nanoTime();

        log.info("Received request for route from {} to {}", request.getFromLinkId(), request.getToLinkId());
        log.info("Thread: {}", Thread.currentThread().getName());
        Integer threadNum = threadNums.computeIfAbsent(Thread.currentThread().getName(), s -> Integer.valueOf(s.substring(s.lastIndexOf('-') + 1)));
        List<ProfilingEntry> pe = profilingEntries.computeIfAbsent(threadNum, s -> new ArrayList<>());

        RoutingRequest raptorRequest = createRaptorRequest(request);
        List<? extends PlanElement> planElements = swissRailRaptor.get().calcRoute(raptorRequest);

        Routing.Response response = convertToProtoResponse(planElements);
        responseObserver.onNext(response);
        responseObserver.onCompleted();

        long endTime = System.nanoTime();

        int travelTime = response.getLegsList().stream().mapToInt(Routing.Leg::getTravTime).sum();
        var p = new ProfilingEntry(threadNum, request.getNow(), request.getDepartureTime(), request.getFromLinkId(), request.getToLinkId(), startTime, endTime - startTime, travelTime);
        pe.add(p);
    }

    private Routing.Response convertToProtoResponse(List<? extends PlanElement> planElements) {
        Routing.Response.Builder responseBuilder = Routing.Response.newBuilder();

        for (PlanElement element : planElements) {
            if (element instanceof Activity activity) {
                responseBuilder.addActivities(convertToProtoActivity(activity));
            } else if (element instanceof Leg leg) {
                responseBuilder.addLegs(convertToProtoLeg(leg));
            } else {
                throw new IllegalArgumentException("Unsupported PlanElement type: " + element.getClass().getName());
            }
        }

        Routing.Response response = responseBuilder.build();
        return response;
    }

    private Routing.Leg convertToProtoLeg(Leg leg) {
        Routing.Leg.Builder legBuilder = Routing.Leg.newBuilder()
                .setMode(leg.getMode())
                .setTravTime((int) leg.getTravelTime().orElseThrow(() -> new IllegalArgumentException("Leg must have travel time")));
        leg.getDepartureTime().ifDefined(d -> legBuilder.setDepTime((int) d));
        Optional.ofNullable(leg.getRoutingMode()).ifPresent(legBuilder::setRoutingMode);

        for (Map.Entry<String, Object> stringObjectEntry : leg.getAttributes().getAsMap().entrySet()) {
            Object value = stringObjectEntry.getValue();
            if (value instanceof String) {
                legBuilder.putAttributes(stringObjectEntry.getKey(), Routing.AttributeValue.newBuilder().setStringValue((String) value).build());
            } else if (value instanceof Double) {
                legBuilder.putAttributes(stringObjectEntry.getKey(), Routing.AttributeValue.newBuilder().setDoubleValue((Double) value).build());
            } else if (value instanceof Integer) {
                legBuilder.putAttributes(stringObjectEntry.getKey(), Routing.AttributeValue.newBuilder().setIntValue((Integer) value).build());
            } else if (value instanceof Boolean) {
                legBuilder.putAttributes(stringObjectEntry.getKey(), Routing.AttributeValue.newBuilder().setBoolValue((Boolean) value).build());
            } else {
                throw new IllegalArgumentException("Unsupported attribute type: " + value.getClass().getName());
            }
        }

        Routing.GenericRoute.Builder protoGenericRoute = Routing.GenericRoute.newBuilder()
                .setStartLink(leg.getRoute().getStartLinkId().toString())
                .setEndLink(leg.getRoute().getEndLinkId().toString())
                .setDistance(leg.getRoute().getDistance());
        leg.getRoute().getTravelTime().ifDefined(d -> protoGenericRoute.setTravTime((int) d));

        if (leg.getRoute() instanceof DefaultTransitPassengerRoute ptRoute) {
            // PT Route
            Routing.PtRoute.Builder protoPtRoute = Routing.PtRoute.newBuilder();
            Routing.PtRouteDescription routeDescription = Routing.PtRouteDescription.newBuilder()
                    .setAccessFacilityId(ptRoute.getAccessStopId().toString())
                    .setEgressFacilityId(ptRoute.getEgressStopId().toString())
                    .setBoardingTime((int) ptRoute.getBoardingTime().orElseThrow(() -> new IllegalArgumentException("PT route must have boarding time")))
                    .setTransitRouteId(ptRoute.getRouteId().toString())
                    .setTransitLineId(ptRoute.getLineId().toString()).build();

            protoPtRoute.setInformation(routeDescription);

            protoPtRoute
                    .setDelegate(protoGenericRoute.build())
                    .build();

            legBuilder.setPtRoute(protoPtRoute);
        } else if (leg.getRoute() instanceof NetworkRoute networkRoute) {
            //Network Route
            Routing.NetworkRoute.Builder protoNetworkRoute = Routing.NetworkRoute.newBuilder();
            for (Id<Link> linkId : networkRoute.getLinkIds()) {
                protoNetworkRoute.addRoute(linkId.toString());
            }
            protoNetworkRoute.setDelegate(protoGenericRoute.build());

            legBuilder.setNetworkRoute(protoNetworkRoute);
        } else {
            //Generic Route
            legBuilder.setGenericRoute(protoGenericRoute);
        }

        return legBuilder.build();
    }

    private Routing.Activity convertToProtoActivity(Activity activity) {
        Routing.Activity.Builder builder = Routing.Activity.newBuilder();
        builder.setActType(activity.getType())
                .setLinkId(activity.getLinkId().toString())
                .setX(activity.getCoord().getX())
                .setY(activity.getCoord().getY());

        activity.getStartTime().ifDefined(t -> builder.setStartTime((int) t));
        activity.getEndTime().ifDefined(t -> builder.setEndTime((int) t));
        activity.getMaximumDuration().ifDefined(d -> builder.setMaxDur((int) d));

        return builder.build();
    }

    @NotNull
    private RoutingRequest createRaptorRequest(Routing.Request request) {
        Id<Link> fromLink = Id.createLinkId(request.getFromLinkId());
        Id<Link> toLink = Id.createLinkId(request.getToLinkId());

        return new RoutingRequest() {
            @Override
            public Facility getFromFacility() {
                return new LinkWrapperFacility(scenario.get().getNetwork().getLinks().get(fromLink));
            }

            @Override
            public Facility getToFacility() {
                return new LinkWrapperFacility(scenario.get().getNetwork().getLinks().get(toLink));
            }

            @Override
            public double getDepartureTime() {
                return request.getDepartureTime();
            }

            @Override
            public Person getPerson() {
                return null;
            }

            @Override
            public Attributes getAttributes() {
                return null;
            }
        };
    }

    private void writeProfilingEntries() {
        DateTimeFormatter dateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd_HH-mm-ss");
        String t = LocalDateTime.now().format(dateTimeFormatter);
        String outputFile = config.controller().getOutputDirectory() + "/routing-profiling-" + t + ".csv";

        log.info("Writing profiling entries to file: {}", outputFile);

        List<ProfilingEntry> allEntries = this.profilingEntries.values().stream().flatMap(Collection::stream).sorted(Comparator.comparingInt(e -> e.simulationNow)).toList();

        try (java.io.BufferedWriter writer = java.nio.file.Files.newBufferedWriter(java.nio.file.Paths.get(outputFile))) {
            writer.write("thread, now, departure_time, from, to, start, duration_ns, travel_time_s");
            writer.newLine();
            for (ProfilingEntry profilingEntry : allEntries) {
                writer.write(profilingEntry.thread + "," + profilingEntry.simulationNow + "," + profilingEntry.departureTime + "," + profilingEntry.from + "," + profilingEntry.to + "," + profilingEntry.duration + "," + profilingEntry.travelTime);
                writer.newLine();
            }
        } catch (java.io.IOException e) {
            log.error("Error writing to file: {}", outputFile, e);
            throw new RuntimeException(e);
        }
    }

    public record Factory(Config config, Runnable shutdown) {
        public RoutingService create() {
            config.controller().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.overwriteExistingFiles);
            // ThreadLocal for Scenario and RoutingModule
            ThreadLocal<Scenario> scenarioThreadLocal = ThreadLocal.withInitial(() -> ScenarioUtils.loadScenario(config));
            ThreadLocal<RoutingModule> raptorThreadLocal = ThreadLocal.withInitial(() -> {
                Scenario scenario = scenarioThreadLocal.get();
                return ControllerUtils.createAdhocInjector(scenario).getInstance(Key.get(RoutingModule.class, Names.named("pt")));
            });
            return new RoutingService(raptorThreadLocal, scenarioThreadLocal, shutdown, config);
        }
    }

    private record ProfilingEntry(int thread, int simulationNow, long departureTime, String from, String to,
                                  long start, long duration, int travelTime) {

    }
}
