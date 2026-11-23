package org.matsim.routing;

import ch.sbb.matsim.routing.pt.raptor.VersionedRaptorTimetable;
import com.google.inject.Injector;
import com.google.inject.Key;
import com.google.inject.name.Names;
import com.google.protobuf.Empty;
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.Coord;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.Activity;
import org.matsim.api.core.v01.population.Leg;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.PlanElement;
import org.matsim.core.population.routes.NetworkRoute;
import org.matsim.core.router.RoutingModule;
import org.matsim.core.router.RoutingRequest;
import org.matsim.facilities.ActivityFacilitiesFactoryImpl;
import org.matsim.facilities.ActivityFacility;
import org.matsim.facilities.Facility;
import org.matsim.pt.routes.DefaultTransitPassengerRoute;
import org.matsim.schemas.io.types.*;
import org.matsim.schemas.services.routing.v1.Request;
import org.matsim.schemas.services.routing.v1.Response;
import org.matsim.schemas.services.routing.v1.RoutingServiceGrpc;
import org.matsim.schemas.services.routing.v1.TimetableVersion;
import org.matsim.utils.objectattributes.attributable.Attributes;
import org.matsim.utils.objectattributes.attributable.AttributesImpl;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicInteger;

import static org.matsim.routing.RoutingUtils.*;

/**
 * Answers the routing requests of the Rust simulation with MATSim's pt router (SwissRailRaptor). Each
 * worker thread has its own router, created by {@link #init()}.
 * <p>
 * Requests and responses are the messages of the routing API {@code matsim/services/routing/v1/routing.proto} of matsim-schemas; legs and activities are the
 * shared types of matsim-schemas. Times are nanoseconds on the wire and seconds in MATSim.
 * <p>
 * With timetable updates, a request that names a version ({@code timetable_version}) waits for it in
 * {@link TimetableVersions} without blocking a thread, then routes on it, and the response names the version. A request
 * waits until its version arrives or the versions fail it (released, iteration over, timetable stream ended or
 * broken). Requests without a version route on the transit schedule. The versions are filled by the
 * {@link TimetableUpdateService}, which {@link RoutingServer} creates next to this service; the two services know only
 * the versions, not each other.
 */
final class RoutingService extends RoutingServiceGrpc.RoutingServiceImplBase {
    private static final Logger log = LogManager.getLogger(RoutingService.class);

    private final ThreadLocal<RoutingModule> router;
    private final Runnable onShutdown;
    /**
     * null without timetable updates
     */
    private final TimetableVersions versions;
    /**
     * Routes the requests that had to wait for their version; threads with their own router.
     */
    private volatile Executor routingExecutor = Runnable::run;
    private final AtomicInteger lastLoggedHour = new AtomicInteger(-1);

    /**
     * @param injector   creates the pt router of each thread; it must bind the {@link RequestTimetableProvider}, see
     *                   {@link RoutingServer#createInjector}
     * @param versions   the timetable versions that requests may name, null without timetable updates
     * @param onShutdown runs, in a new thread, when a client calls {@code Shutdown}
     */
    RoutingService(Injector injector, TimetableVersions versions, Runnable onShutdown) {
        this.router = ThreadLocal.withInitial(() -> injector.getInstance(Key.get(RoutingModule.class, Names.named(ROUTING_MODE))));
        this.versions = versions;
        this.onShutdown = onShutdown;
    }

    /**
     * Sets the threads that route the requests that had to wait for their version, so that routing does not run in
     * the thread of the timetable stream. Their threads must have their router ({@link #init()}).
     */
    void useRoutingExecutor(Executor executor) {
        this.routingExecutor = executor;
    }

    /**
     * Creates the router of the calling thread, so that the first request does not have to.
     */
    void init() {
        router.get();
    }

    @Override
    public void shutdown(Empty request, StreamObserver<Empty> responseObserver) {
        log.info("Received shutdown request");
        responseObserver.onNext(Empty.getDefaultInstance());
        responseObserver.onCompleted();
        new Thread(onShutdown, "router-shutdown").start();
    }

    @Override
    public void getRoute(Request request, StreamObserver<Response> responseObserver) {
        logSimulationHour(nsToS(request.getNowNs()));

        if (!request.hasTimetableVersion()) {
            respond(request, null, null, responseObserver);
            return;
        }
        TimetableVersion version = request.getTimetableVersion();
        if (this.versions == null) {
            sendError(responseObserver, Status.FAILED_PRECONDITION.withDescription("The router runs without timetable updates, but the request names "
                    + "snapshot " + version.getSnapshotId() + " of iteration " + version.getIteration() + "."));
            return;
        }
        CompletableFuture<VersionedRaptorTimetable> timetable = this.versions.get(version.getIteration(), version.getSnapshotId());
        if (timetable.isDone()) {
            // the usual case: route at once in this thread
            timetable.whenComplete((t, e) -> respond(request, t, e, responseObserver));
            return;
        }
        if (responseObserver instanceof ServerCallStreamObserver<Response> call) {
            // a client that gave up (e.g. its deadline) need not be routed for
            call.setOnCancelHandler(() -> timetable.cancel(false));
        }
        // register callback at future; will be called once the future is complete
        timetable.whenCompleteAsync((t, e) -> respond(request, t, e, responseObserver), this.routingExecutor);
    }

    /**
     * Routes the request on {@code timetable} (the schedule if null) and sends the response, or sends the error of the
     * wait for the timetable. Never throws, since it may run as the callback of a future.
     */
    private void respond(Request request, VersionedRaptorTimetable timetable, Throwable error, StreamObserver<Response> responseObserver) {
        if (error != null) {
            Throwable cause = error instanceof CompletionException && error.getCause() != null ? error.getCause() : error;
            if (cause instanceof CancellationException) {
                log.debug("Request {} was cancelled while it waited for its timetable version", request.getRequestId());
                return;
            }
            sendError(responseObserver, Status.FAILED_PRECONDITION.withDescription(cause.getMessage()).withCause(cause));
            return;
        }
        Response response;
        try {
            List<? extends PlanElement> planElements = router.get().calcRoute(toRoutingRequest(request, timetable));
            response = toResponse(planElements, request);
        } catch (RuntimeException e) {
            log.error("Routing failed", e);
            sendError(responseObserver, Status.INTERNAL.withDescription("Routing failed: " + e).withCause(e));
            return;
        }
        try {
            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (RuntimeException e) {
            log.warn("Could not send the response, the call may have been cancelled: {}", e.toString());
        }
    }

    private static void sendError(StreamObserver<Response> responseObserver, Status status) {
        try {
            responseObserver.onError(status.asRuntimeException());
        } catch (RuntimeException e) {
            log.warn("Could not send the error {}, the call may have been cancelled: {}", status, e.toString());
        }
    }

    private void logSimulationHour(int now) {
        int hour = now / SECONDS_PER_HOUR;
        int last = lastLoggedHour.get();
        if (hour > last && lastLoggedHour.compareAndSet(last, hour)) {
            log.info("Received route request for simulation hour {}:00", String.format("%02d", hour));
        }
    }

    /**
     * {@code timetable}, if not null, goes into the routing attributes for the {@link RequestTimetableProvider}.
     */
    private static RoutingRequest toRoutingRequest(Request request, VersionedRaptorTimetable timetable) {
        Id<Link> fromLink = Id.createLinkId(request.getFromLinkId());
        Id<Link> toLink = Id.createLinkId(request.getToLinkId());
        Attributes attributes = new AttributesImpl();
        if (timetable != null) {
            attributes.putAttribute(RequestTimetableProvider.ATTRIBUTE, timetable);
        }

        return new RoutingRequest() {
            @Override
            public Facility getFromFacility() {
                return facility("fromFacility", request.getFrom(), fromLink);
            }

            @Override
            public Facility getToFacility() {
                return facility("toFacility", request.getTo(), toLink);
            }

            @Override
            public double getDepartureTime() {
                return nsToS(request.getDepartureTimeNs());
            }

            @Override
            public Person getPerson() {
                return null;
            }

            @Override
            public Attributes getAttributes() {
                return attributes;
            }
        };
    }

    private static Facility facility(String id, Coordinate coordinate, Id<Link> link) {
        return new ActivityFacilitiesFactoryImpl().createActivityFacility(
                Id.create(id, ActivityFacility.class), new Coord(coordinate.getX(), coordinate.getY()), link);
    }

    private static Response toResponse(List<? extends PlanElement> planElements, Request request) {
        Response.Builder response = Response.newBuilder();
        for (PlanElement element : planElements) {
            if (element instanceof Activity activity) {
                response.addActivities(toProto(activity));
            } else if (element instanceof Leg leg) {
                leg.setRoutingMode(ROUTING_MODE);
                response.addLegs(toProto(leg));
            } else {
                throw new IllegalArgumentException("Unsupported PlanElement type: " + element.getClass().getName());
            }
        }
        if (request.hasTimetableVersion()) {
            response.setTimetableVersion(request.getTimetableVersion());
        }
        return response.setRequestId(request.getRequestId()).build();
    }

    private static org.matsim.schemas.io.types.Leg toProto(Leg leg) {
        org.matsim.schemas.io.types.Leg.Builder builder = org.matsim.schemas.io.types.Leg.newBuilder()
                .setMode(leg.getMode())
                .setTravTimeNs(sToNs(leg.getTravelTime().orElseThrow(() -> new IllegalArgumentException("Leg must have travel time"))));
        leg.getDepartureTime().ifDefined(d -> builder.setDepTimeNs(sToNs(d)));
        Optional.ofNullable(leg.getRoutingMode()).ifPresent(builder::setRoutingMode);

        for (Map.Entry<String, Object> attribute : leg.getAttributes().getAsMap().entrySet()) {
            builder.putAttributes(attribute.getKey(), toProto(attribute.getValue()));
        }

        GenericRoute.Builder genericRoute = GenericRoute.newBuilder()
                .setStartLink(leg.getRoute().getStartLinkId().toString())
                .setEndLink(leg.getRoute().getEndLinkId().toString())
                .setDistance(leg.getRoute().getDistance());
        leg.getRoute().getTravelTime().ifDefined(d -> genericRoute.setTravTimeNs(sToNs(d)));

        if (leg.getRoute() instanceof DefaultTransitPassengerRoute ptRoute) {
            PtRouteDescription description = PtRouteDescription.newBuilder()
                    .setAccessFacilityId(ptRoute.getAccessStopId().toString())
                    .setEgressFacilityId(ptRoute.getEgressStopId().toString())
                    .setBoardingTimeNs(sToNs(ptRoute.getBoardingTime().orElseThrow(() -> new IllegalArgumentException("PT route must have boarding time"))))
                    .setTransitRouteId(ptRoute.getRouteId().toString())
                    .setTransitLineId(ptRoute.getLineId().toString())
                    .build();
            builder.setPtRoute(PtRoute.newBuilder().setDelegate(genericRoute).setInformation(description));
        } else if (leg.getRoute() instanceof NetworkRoute networkRoute) {
            org.matsim.schemas.io.types.NetworkRoute.Builder route = org.matsim.schemas.io.types.NetworkRoute.newBuilder()
                    .setDelegate(genericRoute);
            for (Id<Link> linkId : networkRoute.getLinkIds()) {
                route.addRoute(linkId.toString());
            }
            builder.setNetworkRoute(route);
        } else {
            builder.setGenericRoute(genericRoute);
        }

        return builder.build();
    }

    private static AttributeValue toProto(Object value) {
        return switch (value) {
            case String s -> AttributeValue.newBuilder().setStringValue(s).build();
            case Double d -> AttributeValue.newBuilder().setDoubleValue(d).build();
            case Integer i -> AttributeValue.newBuilder().setIntValue(i).build();
            case Boolean b -> AttributeValue.newBuilder().setBoolValue(b).build();
            default -> throw new IllegalArgumentException("Unsupported attribute type: " + value.getClass().getName());
        };
    }

    private static org.matsim.schemas.io.types.Activity toProto(Activity activity) {
        org.matsim.schemas.io.types.Activity.Builder builder = org.matsim.schemas.io.types.Activity.newBuilder()
                .setActType(activity.getType())
                .setLinkId(activity.getLinkId().toString())
                .setCoordinate(Coordinate.newBuilder().setX(activity.getCoord().getX()).setY(activity.getCoord().getY()));
        activity.getStartTime().ifDefined(t -> builder.setStartTimeNs(sToNs(t)));
        activity.getEndTime().ifDefined(t -> builder.setEndTimeNs(sToNs(t)));
        activity.getMaximumDuration().ifDefined(d -> builder.setMaxDurNs(sToNs(d)));
        return builder.build();
    }
}
