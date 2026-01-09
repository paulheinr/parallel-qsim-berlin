package org.matsim.routing.ph;

import com.google.inject.Injector;
import com.google.inject.Key;
import com.google.inject.name.Names;
import com.google.protobuf.ByteString;
import com.google.protobuf.Empty;
import io.grpc.stub.StreamObserver;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVPrinter;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.jetbrains.annotations.NotNull;
import org.matsim.GitInfo;
import org.matsim.api.core.v01.Coord;
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
import org.matsim.core.router.RoutingModule;
import org.matsim.core.router.RoutingRequest;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.facilities.ActivityFacilitiesFactoryImpl;
import org.matsim.facilities.ActivityFacility;
import org.matsim.facilities.Facility;
import org.matsim.pt.routes.DefaultTransitPassengerRoute;
import org.matsim.utils.objectattributes.attributable.Attributes;
import routing.Routing;
import routing.RoutingServiceGrpc;

import java.io.IOException;
import java.math.BigInteger;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class RoutingServicePH extends RoutingServiceGrpc.RoutingServiceImplBase {
    private static final Logger log = LogManager.getLogger(RoutingServicePH.class);
    private final ThreadLocal<RoutingModule> swissRailRaptor;
    private final Runnable shutdown;
    private final Config config;
    private final ThreadLocal<Integer> threadNum = ThreadLocal.withInitial(() -> {
        String threadName = Thread.currentThread().getName();
        return Integer.valueOf(threadName.substring(threadName.lastIndexOf('-') + 1));
    });
    private final ConcurrentMap<Integer, List<ProfilingEntry>> profilingEntries = new ConcurrentHashMap<>(600_000);
    private int lastNow = -1;

    private RoutingServicePH(ThreadLocal<RoutingModule> raptor, Runnable shutdown, Config config) {
        this.swissRailRaptor = raptor;
        this.shutdown = shutdown;
        this.config = config;
    }

    /**
     * Initializes the service by loading the Swiss Rail Raptor and scenario.
     * This method should be called before any routing requests are processed.
     */
    public void init() {
        threadNum.get();
        swissRailRaptor.get();
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
        List<ProfilingEntry> pe = profilingEntries.computeIfAbsent(threadNum.get(), s -> new ArrayList<>());

        if (threadNum.get() == 0 && lastNow < request.getNow() && lastNow / 3600 != request.getNow() / 3600) {
            log.info("Received route request for simulation hour {}:00", String.format("%02d", request.getNow() / 3600));
            lastNow = request.getNow();
        }

        ByteString requestId = request.getRequestId();

        long startTime = System.nanoTime();
        RoutingRequest raptorRequest = createRaptorRequest(request);
        List<? extends PlanElement> planElements = swissRailRaptor.get().calcRoute(raptorRequest);

        Routing.Response response = convertToProtoResponse(planElements, requestId);
        responseObserver.onNext(response);
        responseObserver.onCompleted();

        long endTime = System.nanoTime();

        int travelTime = response.getLegsList().stream().mapToInt(Routing.Leg::getTravTime).sum();
        var p = new ProfilingEntry(threadNum.get(), request.getNow(), request.getDepartureTime(), request.getFromLinkId(), request.getToLinkId(), startTime, endTime - startTime, travelTime, requestId);
        pe.add(p);
    }

    private Routing.Response convertToProtoResponse(List<? extends PlanElement> planElements, ByteString requestId) {
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

        responseBuilder.setRequestId(requestId);

        return responseBuilder.build();
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
                Id<ActivityFacility> fromFacility = Id.create("fromFacility", ActivityFacility.class);
                Coord from = new Coord(request.getFromX(), request.getFromY());
                return new ActivityFacilitiesFactoryImpl().createActivityFacility(fromFacility, from, fromLink);
            }

            @Override
            public Facility getToFacility() {
                Id<ActivityFacility> fromFacility = Id.create("toFacility", ActivityFacility.class);
                Coord from = new Coord(request.getToX(), request.getToY());
                return new ActivityFacilitiesFactoryImpl().createActivityFacility(fromFacility, from, toLink);
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
        String folder = config.controller().getOutputDirectory() + "/" + GitInfo.commitHash();

        try {
            Files.createDirectories(Path.of(folder));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }

        String outputFile = folder + "/routing-profiling-" + t + ".csv";

        log.info("Writing profiling entries to file: {}", outputFile);

        List<ProfilingEntry> allEntries = this.profilingEntries.values().stream().flatMap(Collection::stream).sorted(Comparator.comparingInt(e -> e.simulationNow)).toList();

        try (java.io.BufferedWriter writer = Files.newBufferedWriter(java.nio.file.Paths.get(outputFile));
             CSVPrinter csv = new CSVPrinter(writer, CSVFormat.DEFAULT.builder().setHeader("thread", "now", "departure_time", "from", "to", "start", "duration_ns", "travel_time_s", "request_id").build())) {
            for (ProfilingEntry profilingEntry : allEntries) {
                csv.printRecord(
                        profilingEntry.thread,
                        profilingEntry.simulationNow,
                        profilingEntry.departureTime,
                        profilingEntry.from,
                        profilingEntry.to,
                        profilingEntry.start,
                        profilingEntry.duration,
                        profilingEntry.travelTime,
                        new BigInteger(1, profilingEntry.requestId.toByteArray()).toString()
                );
            }
        } catch (IOException e) {
            log.error("Error writing to file: {}", outputFile, e);
            throw new RuntimeException(e);
        }
    }

    public record Factory(Config config, Runnable shutdown) {
        public RoutingServicePH create() {
            config.controller().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.overwriteExistingFiles);

            // Serialize config to byte array and create ThreadLocal copies
            // This is necessary because the config is modified during scenario loading (consistency checks are added in Constructor of NewControler),
            // consequently java.util.ConcurrentModificationException MIGHT be thrown (not always)
//            URL context = config.getContext();
//            ByteArrayOutputStream stream = new ByteArrayOutputStream();
//            Writer writer = new OutputStreamWriter(stream);
//            new ConfigWriter(config).writeStream(writer);
//            AtomicReference<byte[]> byteArray = new AtomicReference<>(stream.toByteArray());
//
//            Config config = ThreadLocal.withInitial(() -> {
//                Config cfg = ConfigUtils.createConfig();
//                ConfigReader reader = new ConfigReader(cfg);
//                reader.readStream(new java.io.ByteArrayInputStream(byteArray.get()));
//                cfg.setContext(context);
//                return cfg;
//            });

            // ThreadLocal for Scenario and RoutingModule
            Scenario sc = ScenarioUtils.loadScenario(config);
            Injector adhocInjector = ControllerUtils.createAdhocInjector(sc);
            ThreadLocal<RoutingModule> raptor = ThreadLocal.withInitial(() -> adhocInjector.getInstance(Key.get(RoutingModule.class, Names.named("pt"))));
            return new RoutingServicePH(raptor, shutdown, config);
        }
    }

    private record ProfilingEntry(int thread, int simulationNow, long departureTime, String from, String to,
                                  long start, long duration, int travelTime, ByteString requestId) {

    }
}
