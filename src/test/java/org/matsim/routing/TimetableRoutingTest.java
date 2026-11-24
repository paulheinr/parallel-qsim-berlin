package org.matsim.routing;

import ch.sbb.matsim.config.SwissRailRaptorConfigGroup;
import com.google.protobuf.Empty;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.matsim.api.core.v01.Coord;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.population.Leg;
import org.matsim.api.core.v01.population.PlanElement;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.router.DefaultRoutingRequest;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.utils.io.IOUtils;
import org.matsim.examples.ExamplesUtils;
import org.matsim.facilities.ActivityFacilitiesFactoryImpl;
import org.matsim.facilities.ActivityFacility;
import org.matsim.facilities.Facility;
import org.matsim.pt.routes.TransitPassengerRoute;
import org.matsim.routing.TimetableMessages.SnapshotZero;
import org.matsim.schemas.io.types.Coordinate;
import org.matsim.schemas.io.types.PtRouteDescription;
import org.matsim.schemas.services.routing.v1.*;
import org.matsim.utils.objectattributes.attributable.AttributesImpl;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.matsim.routing.TimetableMessages.delta;
import static org.matsim.routing.TimetableMessages.ns;
import static org.matsim.routing.TimetableMessages.start;
import static org.matsim.routing.TimetableMessages.version;

/**
 * Requests that name a timetable version, on pt-tutorial, without a network: the timetable stream and the requests go
 * directly to the {@link RoutingService}, whose routing executor runs the waiting requests in the thread that completes
 * them. Snapshot 0 is the transit schedule.
 */
class TimetableRoutingTest {

    /**
     * The request of {@link RoutingServerTest}: from link 1112 to 4142 at 7:32:06, with a pt leg.
     */
    private static final int DEPARTURE_TIME = 27126;
    private static final int DELAY = 60;

    @TempDir
    Path output;

    @Test
    void snapshotZeroRoutesLikeTheSchedule() throws IOException {
        Router router = new Router(config(true));

        Answer plain = router.route(null);
        Answer onVersion = router.route(version(0, 0));

        assertNotNull(plain.response);
        assertEquals(plain.response.getLegsList(), onVersion.response.getLegsList());
        assertEquals(plain.response.getActivitiesList(), onVersion.response.getActivitiesList());
        assertEquals(version(0, 0), onVersion.response.getTimetableVersion());
        assertFalse(plain.response.hasTimetableVersion());
    }

    @Test
    void requestsWaitForTheirSnapshot() throws IOException {
        Router router = new Router(config(true));
        PtRouteDescription boarded = ptRoute(router.route(null).response);
        int boardingTime = RoutingUtils.nsToS(boarded.getBoardingTimeNs());
        int external = router.snapshot.external(boarded.getTransitRouteId(), boarded.getAccessFacilityId(), boardingTime);

        Answer waiting = router.route(version(0, 1));
        assertNull(waiting.response);
        assertNull(waiting.error);

        router.updateStream.onNext(delta(0, 1, 0, router.snapshot.delayed(external, DELAY)));

        assertTrue(waiting.completed);
        assertEquals(boarded.getTransitRouteId(), ptRoute(waiting.response).getTransitRouteId());
        assertEquals(boardingTime + DELAY, RoutingUtils.nsToS(ptRoute(waiting.response).getBoardingTimeNs()));
        assertEquals(version(0, 1), waiting.response.getTimetableVersion());
    }

    @Test
    void theEndOfTheStreamFailsWaitingRequests() throws IOException {
        Router router = new Router(config(true));
        Answer waiting = router.route(version(0, 1));

        router.updateStream.onCompleted();

        assertEquals(Status.Code.FAILED_PRECONDITION, Status.fromThrowable(waiting.error).getCode());
    }

    @Test
    void releasedSnapshotsFail() throws IOException {
        Router router = new Router(config(true));
        router.updateStream.onNext(delta(0, 1, 0));
        router.updateStream.onNext(delta(0, 2, 2));

        Answer released = router.route(version(0, 1));

        assertEquals(Status.Code.FAILED_PRECONDITION, Status.fromThrowable(released.error).getCode());
        assertNotNull(router.route(version(0, 2)).response);
    }

    @Test
    void aRouterWithoutTimetableUpdatesRejectsVersions() throws IOException {
        RoutingServer.Services services = RoutingServer.createServices(config(false), () -> {
        });
        assertTrue(services.timetable().isEmpty());

        Answer answer = new Answer();
        services.routing().getRoute(request(version(0, 0)), answer);

        assertEquals(Status.Code.FAILED_PRECONDITION, Status.fromThrowable(answer.error).getCode());
    }

    /**
     * Creates a config for the pt-tutorial scenario.
     */
    private Config config(boolean timetableUpdates) throws IOException {
        var scenario = ExamplesUtils.getTestScenarioURL("pt-tutorial");
        Config config = RoutingServer.prepareConfig(ConfigUtils.loadConfig(IOUtils.extendUrl(scenario, "0.config.xml")), this.output);
        ConfigUtils.addOrGetModule(config, SwissRailRaptorConfigGroup.class).setUseTimetableUpdates(timetableUpdates);
        return config;
    }

    /**
     * A router with timetable updates whose stream has sent snapshot 0 and started iteration 0.
     */
    private static final class Router {
        final RoutingService routingService;
        final SnapshotZero snapshot;
        final StreamObserver<TimetableUpdate> updateStream;

        Router(Config config) {
            RoutingServer.Services services = RoutingServer.createServices(config, () -> {
            });
            this.routingService = services.routing();
            this.snapshot = new SnapshotZero(ScenarioUtils.loadScenario(config).getTransitSchedule());

            this.updateStream = services.timetable().orElseThrow().updateTimetable(new StreamObserver<>() {
                // create empty response observer
                @Override
                public void onNext(Empty value) {
                }

                @Override
                public void onError(Throwable t) {
                    throw new AssertionError("The timetable stream failed", t);
                }

                @Override
                public void onCompleted() {
                }
            });
            this.snapshot.messages().forEach(this.updateStream::onNext);
            this.updateStream.onNext(start(0));
        }

        Answer route(TimetableVersion version) {
            Answer answer = new Answer();
            this.routingService.getRoute(request(version), answer);
            return answer;
        }
    }

    private static Request request(TimetableVersion version) {
        Request.Builder request = Request.newBuilder()
                .setPersonId("1")
                .setFromLinkId("1112")
                .setFrom(Coordinate.newBuilder().setX(1000).setY(1500))
                .setToLinkId("4142")
                .setTo(Coordinate.newBuilder().setX(4000).setY(1500))
                .setMode(RoutingUtils.ROUTING_MODE)
                .setDepartureTimeNs(ns(DEPARTURE_TIME))
                .setNowNs(ns(27000));
        if (version != null) {
            request.setTimetableVersion(version);
        }
        return request.build();
    }

    /**
     * The request of {@link #request(TimetableVersion)} for the routing module, with {@code attributes}.
     */
    private static org.matsim.core.router.RoutingRequest request(AttributesImpl attributes) {
        return DefaultRoutingRequest.of(facility("from", new Coord(1000, 1500), "1112"), facility("to", new Coord(4000, 1500), "4142"), DEPARTURE_TIME,
                null, attributes);
    }

    private static Facility facility(String id, Coord coord, String link) {
        return new ActivityFacilitiesFactoryImpl().createActivityFacility(Id.create(id, ActivityFacility.class), coord, Id.createLinkId(link));
    }

    private static TransitPassengerRoute ptRoute(List<? extends PlanElement> elements) {
        for (PlanElement element : elements) {
            if (element instanceof Leg leg && leg.getRoute() instanceof TransitPassengerRoute route) {
                return route;
            }
        }
        throw new AssertionError("No pt leg: " + elements);
    }

    private static PtRouteDescription ptRoute(Response response) {
        return response.getLegsList().stream().filter(org.matsim.schemas.io.types.Leg::hasPtRoute).findFirst()
                .orElseThrow(() -> new AssertionError("No pt leg: " + response)).getPtRoute().getInformation();
    }

    /**
     * Records the answer of the router to a request.
     */
    private static final class Answer implements StreamObserver<Response> {
        Response response;
        Throwable error;
        boolean completed = false;

        @Override
        public void onNext(Response value) {
            this.response = value;
        }

        @Override
        public void onError(Throwable t) {
            this.error = t;
        }

        @Override
        public void onCompleted() {
            this.completed = true;
        }
    }
}
