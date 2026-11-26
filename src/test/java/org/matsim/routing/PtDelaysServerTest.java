package org.matsim.routing;

import com.google.common.util.concurrent.ListenableFuture;
import com.google.protobuf.Empty;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.health.v1.HealthCheckRequest;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.health.v1.HealthGrpc;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.router.TripStructureUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.pt.routes.TransitPassengerRoute;
import org.matsim.schemas.io.types.Coordinate;
import org.matsim.schemas.io.types.PtRouteDescription;
import org.matsim.schemas.services.routing.v1.*;

import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;
import static org.matsim.routing.TimetableMessages.*;

/**
 * The router with timetable updates over gRPC, on the scenario {@code integration/pt-delays} (see its README): the
 * server of {@link RoutingServer#start}, the timetable stream and the requests as the simulation sends them. The
 * requests are the trips of the persons of the scenario; snapshot 0 is the transit schedule.
 * <p>
 * Stream messages arrive at the router asynchronously. Before an assertion that needs a state, a test waits for the
 * answer to a request for the newest snapshot: the stream is ordered, so all earlier messages have been applied then.
 */
@Timeout(60)
class PtDelaysServerTest {

    private static final Path INPUT = Path.of("integration/pt-delays/input");
    private static final int THREADS = 2;

    private static final String EXPRESS_PERSON = "takes_later_but_faster_express";
    private static final String TRANSFERS_PERSON = "transfers_with_two_minutes_at_hub";
    private static final String WAITS_PERSON = "waits_at_hub_after_just_missing_trunk";
    private static final String STARTS_AT_HUB_PERSON = "starts_at_hub_after_trunk_departed";

    /**
     * The route of {@link #TRANSFERS_PERSON} with feeder_0800 3 minutes late: it reaches hub at 08:09, after trunk_0808 left.
     * local_0800 passes hub at 08:10 and reaches center at 08:20, one minute before trunk_0815.
     */
    private static final List<PtLeg> FEEDER_0800_LATE = List.of(
            PtLeg.of("feeder", "feeder_village_hub", "village", "hub", "08:03"),
            PtLeg.of("local", "local_suburb_center", "hub", "center", "08:10"));

    /**
     * A pt leg as the plans and the responses describe it.
     */
    record PtLeg(String line, String route, String from, String to, int boardingTime) {
        static PtLeg of(String line, String route, String from, String to, String boardingTime) {
            String[] hm = boardingTime.split(":");
            return new PtLeg(line, route, from, to, Integer.parseInt(hm[0]) * 3600 + Integer.parseInt(hm[1]) * 60);
        }
    }

    @TempDir
    Path output;

    private RoutingServer.Running routerServer;

    // Channel to the router, which serves the RoutingService, the TimetableService and the health service
    private ManagedChannel channel;
    private Population population;
    private SnapshotZero snapshot;

    // Receives the only answer of the router to the timetable stream, at its end: Empty after onCompleted,
    // or the error of a broken contract (see awaitError).
    private StreamAnswer timetableUpdateAnswerStream;
    // The sending side of the timetable stream: onNext sends a message to the router.
    private StreamObserver<TimetableUpdate> timetableUpdateStream;

    /**
     * Starts a router with {@link #THREADS} threads on a free port of the loopback address (see
     * {@link RoutingServer#start(Config, InetSocketAddress, int)}), opens the timetable stream and sends snapshot 0 and
     * the start of iteration 0, so every test begins with version (0, 0).
     */
    @BeforeEach
    void setUp() throws Exception {
        Config config = RoutingServer.prepareConfig(ConfigUtils.loadConfig(INPUT.resolve("router-config.xml").toString()), this.output);
        InetAddress loopback = InetAddress.getLoopbackAddress();
        this.routerServer = RoutingServer.start(config, new InetSocketAddress(loopback, 0), THREADS);
        this.channel = ManagedChannelBuilder.forAddress(loopback.getHostAddress(), this.routerServer.port()).usePlaintext().build();
        this.population = PopulationUtils.readPopulation(INPUT.resolve("plans.xml").toString());

        this.snapshot = new SnapshotZero(ScenarioUtils.loadScenario(config).getTransitSchedule());

        this.timetableUpdateAnswerStream = new StreamAnswer();
        this.timetableUpdateStream = TimetableServiceGrpc.newStub(this.channel).updateTimetable(this.timetableUpdateAnswerStream);
        this.snapshot.messages().forEach(this.timetableUpdateStream::onNext);
        this.timetableUpdateStream.onNext(start(0));
    }

    @AfterEach
    void tearDown() {
        try {
            this.timetableUpdateStream.onCompleted();
        } catch (RuntimeException e) {
            // the stream may already have ended with an error
        }
        this.channel.shutdownNow();
        this.routerServer.stop();
    }

    /**
     * Without delays, every person gets the pt legs of its plan, which were derived by hand.
     */
    @Test
    void baseCase() {
        for (Person person : this.population.getPersons().values()) {
            String id = person.getId().toString();
            assertEquals(plannedPtLegs(id), ptLegs(route(id, version(0, 0))), id);
        }
    }

    /**
     * The delay variants of the README, each as the delta of snapshot 1. Snapshot 0 keeps the base case.
     */
    @ParameterizedTest(name = "{0}")
    @MethodSource("delayVariants")
    void delayVariants(String variant, String departure, int delay, String person, List<PtLeg> expected) {
        this.timetableUpdateStream.onNext(delta(0, 1, 0, this.snapshot.delayed(departure, delay)));

        assertEquals(expected, ptLegs(route(person, version(0, 1))));
        assertEquals(plannedPtLegs(person), ptLegs(route(person, version(0, 0))), "the old version keeps its result");
    }

    static Stream<Arguments> delayVariants() {
        PtLeg feeder0810 = PtLeg.of("feeder", "feeder_village_hub", "village", "hub", "08:10");
        return Stream.of(
                // the chosen express is no longer the fastest connection
                Arguments.of("express_0805_late", "express_0805", 10 * 60, EXPRESS_PERSON,
                        List.of(PtLeg.of("local", "local_suburb_center", "suburb", "center", "08:00"))),
                // the connection to trunk_0808 is lost
                Arguments.of("feeder_0800_late", "feeder_0800", 3 * 60, TRANSFERS_PERSON, FEEDER_0800_LATE),
                // a connection missed before becomes reachable
                Arguments.of("trunk_0815_late_2min", "trunk_0815", 2 * 60, WAITS_PERSON,
                        List.of(feeder0810, PtLeg.of("trunk", "trunk_hub_center", "hub", "center", "08:17"))),
                // a departure that left on schedule is still there
                Arguments.of("trunk_0815_late_5min", "trunk_0815", 5 * 60, STARTS_AT_HUB_PERSON,
                        List.of(PtLeg.of("trunk", "trunk_hub_center", "hub", "center", "08:20"))));
    }

    /**
     * local_0800 5 minutes late alone would overtake local_0802: the router ends the stream.
     */
    @Test
    void delayingLocal0800AloneBreaksTheContract() throws InterruptedException {
        this.timetableUpdateStream.onNext(delta(0, 1, 0, this.snapshot.delayed("local_0800", 5 * 60)));

        assertEquals(Status.Code.INVALID_ARGUMENT, this.timetableUpdateAnswerStream.awaitError().getCode());
    }

    /**
     * The variant local_0800_late of the README: local_0802 stays behind local_0800, which the router accepts.
     */
    @Test
    void local0802StaysBehindLocal0800() {
        this.timetableUpdateStream.onNext(delta(0, 1, 0, this.snapshot.delayed("local_0800", 5 * 60), this.snapshot.delayed("local_0802", 3 * 60)));

        assertEquals(plannedPtLegs(EXPRESS_PERSON), ptLegs(route(EXPRESS_PERSON, version(0, 1))));
        assertNull(this.timetableUpdateAnswerStream.error);
    }

    /**
     * Requests that wait for their version occupy no router thread.
     */
    @Test
    void waitingRequestsLeaveTheThreadsFree() throws Exception {
        List<ListenableFuture<Response>> waiting = new ArrayList<>();
        for (int i = 0; i < 2 * THREADS; i++) {
            waiting.add(RoutingServiceGrpc.newFutureStub(this.channel).getRoute(request(TRANSFERS_PERSON, version(0, 1))));
        }

        assertEquals(plannedPtLegs(TRANSFERS_PERSON), ptLegs(route(TRANSFERS_PERSON, version(0, 0))));
        assertTrue(waiting.stream().noneMatch(ListenableFuture::isDone));

        this.timetableUpdateStream.onNext(delta(0, 1, 0, this.snapshot.delayed("feeder_0800", 3 * 60)));
        for (ListenableFuture<Response> answer : waiting) {
            assertEquals(FEEDER_0800_LATE, ptLegs(answer.get(10, TimeUnit.SECONDS)));
        }
    }

    /**
     * A request for a snapshot that does not come waits until the deadline of the client.
     */
    @Test
    void aClientDeadlineEndsTheWait() {
        StatusRuntimeException e = assertThrows(StatusRuntimeException.class, () -> RoutingServiceGrpc.newBlockingStub(this.channel)
                .withDeadlineAfter(500, TimeUnit.MILLISECONDS).getRoute(request(TRANSFERS_PERSON, version(0, 5))));

        assertEquals(Status.Code.DEADLINE_EXCEEDED, e.getStatus().getCode());
        assertEquals(plannedPtLegs(TRANSFERS_PERSON), ptLegs(route(TRANSFERS_PERSON, version(0, 0))));
    }

    /**
     * A request for a version that the simulation has released fails at once with FAILED_PRECONDITION instead of
     * waiting until its deadline.
     */
    @Test
    void releasedVersionsFailAtOnce() {
        this.timetableUpdateStream.onNext(delta(0, 1, 0));
        // the oldest needed snapshot is 2: the router releases snapshots 0 and 1
        this.timetableUpdateStream.onNext(delta(0, 2, 2));

        // Waits until both updates are processed (and thus snapshot 1 released): the router answers on (0, 2) only
        // after it has applied delta 2, which releases the older snapshots in the same step.
        route(TRANSFERS_PERSON, version(0, 2));

        // ask for snapshot 1, which is already released
        StatusRuntimeException e = assertThrows(StatusRuntimeException.class, () -> route(TRANSFERS_PERSON, version(0, 1)));

        assertEquals(Status.Code.FAILED_PRECONDITION, e.getStatus().getCode());
    }

    /**
     * The start of iteration 1 fails the requests that still wait for a snapshot of iteration 0. Iteration 1 begins
     * on snapshot 0 again, and a request for one of its later snapshots waits for it.
     */
    @Test
    void theNextIterationStartsOnSnapshotZero() throws Exception {
        ListenableFuture<Response> neverSent = RoutingServiceGrpc.newFutureStub(this.channel).getRoute(request(TRANSFERS_PERSON, version(0, 5)));
        ListenableFuture<Response> nextIteration = RoutingServiceGrpc.newFutureStub(this.channel).getRoute(request(TRANSFERS_PERSON, version(1, 1)));
        this.timetableUpdateStream.onNext(delta(0, 1, 0, this.snapshot.delayed("feeder_0800", 3 * 60)));

        this.timetableUpdateStream.onNext(start(1));

        ExecutionException e = assertThrows(ExecutionException.class, () -> neverSent.get(10, TimeUnit.SECONDS));
        assertEquals(Status.Code.FAILED_PRECONDITION, Status.fromThrowable(e.getCause()).getCode());
        assertEquals(plannedPtLegs(TRANSFERS_PERSON), ptLegs(route(TRANSFERS_PERSON, version(1, 0))));
        assertFalse(nextIteration.isDone());

        this.timetableUpdateStream.onNext(delta(1, 1, 0, this.snapshot.delayed("feeder_0800", 3 * 60)));
        assertEquals(FEEDER_0800_LATE, ptLegs(nextIteration.get(10, TimeUnit.SECONDS)));
    }

    /**
     * A delta that skips a snapshot breaks the contract: the router ends the stream with INVALID_ARGUMENT. After that,
     * requests with a version fail, those without one still route.
     */
    @Test
    void aBrokenContractEndsTheStream() throws InterruptedException {
        this.timetableUpdateStream.onNext(delta(0, 2, 0));

        assertEquals(Status.Code.INVALID_ARGUMENT, this.timetableUpdateAnswerStream.awaitError().getCode());
        StatusRuntimeException e = assertThrows(StatusRuntimeException.class, () -> route(TRANSFERS_PERSON, version(0, 0)));
        assertEquals(Status.Code.FAILED_PRECONDITION, e.getStatus().getCode());
        assertEquals(plannedPtLegs(TRANSFERS_PERSON), ptLegs(route(TRANSFERS_PERSON, null)), "requests without a version still route");
    }

    /**
     * With timetable updates, the health service reports the TimetableService as serving, besides the RoutingService.
     */
    @Test
    void reportsTheTimetableServiceAsServing() {
        assertEquals(ServingStatus.SERVING, HealthGrpc.newBlockingStub(this.channel)
                .check(HealthCheckRequest.newBuilder().setService(TimetableServiceGrpc.SERVICE_NAME).build()).getStatus());
    }

    /**
     * Routes the trip of {@code person} and waits for the answer, at most 10 s.
     */
    private Response route(String person, TimetableVersion version) {
        return RoutingServiceGrpc.newBlockingStub(this.channel).withDeadlineAfter(10, TimeUnit.SECONDS).getRoute(request(person, version));
    }

    /**
     * The trip of {@code person}: from its home, when it ends, to its work.
     */
    private Request request(String person, TimetableVersion version) {
        List<Activity> activities = TripStructureUtils.getActivities(plan(person), TripStructureUtils.StageActivityHandling.ExcludeStageActivities);
        Activity home = activities.getFirst();
        Activity work = activities.getLast();
        long departure = ns((int) home.getEndTime().seconds());
        Request.Builder request = Request.newBuilder()
                .setPersonId(person)
                .setFromLinkId(home.getLinkId().toString())
                .setFrom(Coordinate.newBuilder().setX(home.getCoord().getX()).setY(home.getCoord().getY()))
                .setToLinkId(work.getLinkId().toString())
                .setTo(Coordinate.newBuilder().setX(work.getCoord().getX()).setY(work.getCoord().getY()))
                .setMode(RoutingUtils.ROUTING_MODE)
                .setDepartureTimeNs(departure)
                .setNowNs(departure);
        if (version != null) {
            request.setTimetableVersion(version);
        }
        return request.build();
    }

    private Plan plan(String person) {
        return this.population.getPersons().get(Id.createPersonId(person)).getSelectedPlan();
    }

    /**
     * The pt legs of the plan of {@code person} in plans.xml.
     */
    private List<PtLeg> plannedPtLegs(String person) {
        List<PtLeg> legs = new ArrayList<>();
        for (Leg leg : TripStructureUtils.getLegs(plan(person))) {
            if (leg.getRoute() instanceof TransitPassengerRoute route) {
                legs.add(new PtLeg(route.getLineId().toString(), route.getRouteId().toString(), route.getAccessStopId().toString(),
                        route.getEgressStopId().toString(), (int) route.getBoardingTime().seconds()));
            }
        }
        return legs;
    }

    /**
     * The pt legs of {@code response} in the form of {@link #plannedPtLegs}, so that both can be compared.
     */
    private static List<PtLeg> ptLegs(Response response) {
        List<PtLeg> legs = new ArrayList<>();
        for (org.matsim.schemas.io.types.Leg leg : response.getLegsList()) {
            if (leg.hasPtRoute()) {
                PtRouteDescription route = leg.getPtRoute().getInformation();
                legs.add(new PtLeg(route.getTransitLineId(), route.getTransitRouteId(), route.getAccessFacilityId(), route.getEgressFacilityId(),
                        RoutingUtils.nsToS(route.getBoardingTimeNs())));
            }
        }
        return legs;
    }

    /**
     * Records how the router ends the timetable stream.
     */
    private static final class StreamAnswer implements StreamObserver<Empty> {
        private final CountDownLatch ended = new CountDownLatch(1);
        volatile Throwable error;

        @Override
        public void onNext(Empty value) {
        }

        @Override
        public void onError(Throwable t) {
            this.error = t;
            this.ended.countDown();
        }

        @Override
        public void onCompleted() {
            this.ended.countDown();
        }

        /**
         * @return the status of the error that ended the stream, waiting for it at most 10 s
         */
        Status awaitError() throws InterruptedException {
            assertTrue(this.ended.await(10, TimeUnit.SECONDS), "the stream did not end");
            assertInstanceOf(StatusRuntimeException.class, this.error);
            return Status.fromThrowable(this.error);
        }
    }
}
