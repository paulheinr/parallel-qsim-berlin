package org.matsim.routing;

import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptor;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.inject.Key;
import com.google.inject.name.Names;
import general.General;
import io.grpc.stub.StreamObserver;
import org.apache.commons.math3.util.Pair;
import org.jetbrains.annotations.NotNull;
import org.matsim.IdStoreDeserializer;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.Activity;
import org.matsim.api.core.v01.population.Leg;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.PlanElement;
import org.matsim.core.config.Config;
import org.matsim.core.controler.Controller;
import org.matsim.core.controler.ControllerUtils;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.router.LinkWrapperFacility;
import org.matsim.core.router.RoutingModule;
import org.matsim.core.router.RoutingRequest;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.facilities.Facility;
import org.matsim.pt.routes.DefaultTransitPassengerRoute;
import org.matsim.utils.objectattributes.attributable.Attributes;
import population.Population;
import routing.Routing;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

public class RoutingService extends routing.RoutingServiceGrpc.RoutingServiceImplBase {
    private final RoutingModule swissRailRaptor;
    private final Scenario scenario;

    private RoutingService(RoutingModule wrappedRaptorRouter, Scenario scenario) {
        this.swissRailRaptor = wrappedRaptorRouter;
        this.scenario = scenario;
    }

    @Override
    public void getRoute(Routing.Request request, StreamObserver<Routing.Response> responseObserver) {
        System.out.println("Received request for route from " + request.getFromLinkId() + " to " + request.getToLinkId());

        RoutingRequest raptorRequest = createRaptorRequest(request);
        List<? extends PlanElement> planElements = swissRailRaptor.calcRoute(raptorRequest);

        Routing.Response response = convertToProtoResponse(planElements);
        responseObserver.onNext(response);
        responseObserver.onCompleted();
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

        return responseBuilder.build();
    }

    private Population.Leg convertToProtoLeg(Leg leg) {
        Population.Leg.Builder legBuilder = Population.Leg.newBuilder()
        .setMode(Id.create(leg.getMode(), String.class).index())
        .setRoutingMode(Id.create(leg.getRoutingMode(), String.class).index())
        .setTravTime((int) leg.getTravelTime().orElseThrow(() -> new IllegalArgumentException("Leg must have travel time")));
        leg.getDepartureTime().ifDefined(d -> legBuilder.setDepTime((int) d));

        for (Map.Entry<String, Object> stringObjectEntry : leg.getAttributes().getAsMap().entrySet()) {
            Object value = stringObjectEntry.getValue();
            if (value instanceof String) {
                legBuilder.putAttributes(stringObjectEntry.getKey(), General.AttributeValue.newBuilder().setStringValue((String) value).build());
            } else if (value instanceof Double) {
                legBuilder.putAttributes(stringObjectEntry.getKey(), General.AttributeValue.newBuilder().setDoubleValue((Double) value).build());
            } else if (value instanceof Integer) {
                legBuilder.putAttributes(stringObjectEntry.getKey(), General.AttributeValue.newBuilder().setIntValue((Integer) value).build());
            } else if (value instanceof Boolean) {
                legBuilder.putAttributes(stringObjectEntry.getKey(), General.AttributeValue.newBuilder().setBoolValue((Boolean) value).build());
            } else {
                throw new IllegalArgumentException("Unsupported attribute type: " + value.getClass().getName());
            }
        }

        Population.GenericRoute.Builder protoGenericRoute = Population.GenericRoute.newBuilder()
                .setStartLink(leg.getRoute().getStartLinkId().index())
                .setEndLink(leg.getRoute().getEndLinkId().index())
                .setDistance(leg.getRoute().getDistance());
        leg.getRoute().getTravelTime().ifDefined(d -> protoGenericRoute.setTravTime((int) d));

        DefaultTransitPassengerRoute ptRoute = (DefaultTransitPassengerRoute) leg.getRoute();
        Population.PtRouteDescription routeDescription = Population.PtRouteDescription.newBuilder()
                .setAccessFacilityId(ptRoute.getAccessStopId().toString())
                .setEgressFacilityId(ptRoute.getEgressStopId().toString())
                .setBoardingTime((int) ptRoute.getBoardingTime().orElseThrow(() -> new IllegalArgumentException("PT route must have boarding time")))
                .setTransitRouteId(ptRoute.getRouteId().toString())
                .setTransitLineId(ptRoute.getLineId().toString()).build();


        Population.PtRoute protoPtRoute = Population.PtRoute.newBuilder()
                .setInformation(routeDescription)
                .setDelegate(protoGenericRoute.build())
                .build();

        legBuilder.setPtRoute(protoPtRoute);

        return legBuilder.build();
    }

    private Population.Activity convertToProtoActivity(Activity activity) {
        Population.Activity.Builder builder = Population.Activity.newBuilder();
        builder.setActType(Id.create(activity.getType(), String.class).index())
                .setLinkId(activity.getLinkId().index())
                .setX(activity.getCoord().getX())
                .setY(activity.getCoord().getY());

        activity.getStartTime().ifDefined(t -> builder.setStartTime((int) t));
        activity.getEndTime().ifDefined(t -> builder.setEndTime((int) t));
        activity.getMaximumDuration().ifDefined(d -> builder.setMaxDur((int) d));

        return builder.build();
    }

    @NotNull
    private RoutingRequest createRaptorRequest(Routing.Request request) {
        Id<Link> fromLink = Id.get(Math.toIntExact(request.getFromLinkId()), Link.class);
        Id<Link> toLink = Id.get(Math.toIntExact(request.getToLinkId()), Link.class);

        return new RoutingRequest() {
            @Override
            public Facility getFromFacility() {
                return new LinkWrapperFacility(scenario.getNetwork().getLinks().get(fromLink));
            }

            @Override
            public Facility getToFacility() {
                return new LinkWrapperFacility(scenario.getNetwork().getLinks().get(toLink));
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

    public static class Factory{
        private final Path idPath;
        private final Config config;

        public Factory(Config config, Path idPath) {
            this.idPath = idPath;
            this.config = config;
        }

        public RoutingService create() {
            Map<Long, List<String>> ids = IdStoreDeserializer.loadIdStore(idPath);
            createMatsimIds(ids);
            config.controller().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.deleteDirectoryIfExists);
            Scenario scenario = ScenarioUtils.loadScenario(config);
            Controller controller = ControllerUtils.createController(scenario);

            RoutingModule swissRailRaptor = controller.getInjector().getInstance(Key.get(RoutingModule.class, Names.named("pt")));

            return new RoutingService(swissRailRaptor, scenario);
        }

        private void createMatsimIds(Map<Long, List<String>> ids){
            for (Map.Entry<Long, List<String>> idEntry : ids.entrySet()) {
                Long type = idEntry.getKey();
                Class<?> typeClass = IdStoreDeserializer.TYPE_ID_TO_CLASS.get(type);

                if (typeClass == null) {
                    throw new IllegalArgumentException("Unknown type ID: " + type);
                }

                List<String> externalIds = idEntry.getValue();
                for (String externalId : externalIds) {
                    Id.create(externalId, typeClass);
                }
            }
        }
    }
}
