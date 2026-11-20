package org.matsim.routing;

import ch.sbb.matsim.routing.pt.raptor.RaptorStaticConfig;
import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptor;
import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptorData;
import ch.sbb.matsim.routing.pt.raptor.VersionedRaptorTimetable;
import com.google.protobuf.Empty;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.matsim.api.core.v01.Coord;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.Leg;
import org.matsim.api.core.v01.population.PlanElement;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.population.routes.RouteUtils;
import org.matsim.core.router.DefaultRoutingRequest;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.facilities.ActivityFacilitiesFactoryImpl;
import org.matsim.facilities.ActivityFacility;
import org.matsim.facilities.Facility;
import org.matsim.pt.routes.TransitPassengerRoute;
import org.matsim.pt.transitSchedule.api.TransitLine;
import org.matsim.pt.transitSchedule.api.TransitRoute;
import org.matsim.pt.transitSchedule.api.TransitRouteStop;
import org.matsim.pt.transitSchedule.api.TransitSchedule;
import org.matsim.pt.transitSchedule.api.TransitScheduleFactory;
import org.matsim.pt.transitSchedule.api.TransitStopFacility;
import org.matsim.schemas.services.routing.v1.BaseDeparture;
import org.matsim.schemas.services.routing.v1.BaseRoute;
import org.matsim.schemas.services.routing.v1.IterationStart;
import org.matsim.schemas.services.routing.v1.TimetableDelta;
import org.matsim.schemas.services.routing.v1.TimetableUpdate;
import org.matsim.schemas.services.routing.v1.TripUpdate;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The timetable stream without a network: messages go directly to the observer of {@link TimetableUpdateService},
 * and the versions are read from {@link TimetableVersions}. The times of a version are checked by routing on it.
 * <p>
 * Route 1 runs A-X-B (10 min per hop) with departures 1a at 8:00 and 1b at 9:00, route 2 runs X-C with 2a at 8:30.
 * In snapshot 0, 1a leaves 2 minutes late. The stops are 10 km apart, so walking never wins. External departure
 * numbers: 1a = 0, 1b = 1, 2a = 2.
 */
class TimetableUpdateServiceTest {

	private static final int H = 3600;
	private static final int M = 60;
	private static final int DEP_1A = 0;

	private final Config config = ConfigUtils.createConfig();
	private TransitStopFacility a;
	private TransitStopFacility b;
	private SwissRailRaptorData data;
	private TimetableVersions versions;
	private Recorder response;
	private StreamObserver<TimetableUpdate> stream;

	@BeforeEach
	void setUp() {
		Scenario scenario = ScenarioUtils.createScenario(this.config);
		TransitSchedule schedule = scenario.getTransitSchedule();
		TransitScheduleFactory factory = schedule.getFactory();
		Id<Link> link = Id.createLinkId("link");
		this.a = stop(schedule, link, "A", 0, 0);
		TransitStopFacility x = stop(schedule, link, "X", 10_000, 0);
		this.b = stop(schedule, link, "B", 20_000, 0);
		TransitStopFacility c = stop(schedule, link, "C", 10_000, 10_000);
		route(schedule, factory, link, "1", List.of(this.a, x, this.b), List.of(0, 10 * M, 20 * M), "1a", 8 * H, "1b", 9 * H);
		route(schedule, factory, link, "2", List.of(x, c), List.of(0, 10 * M), "2a", 8 * H + 30 * M);

		RaptorStaticConfig raptorConfig = new RaptorStaticConfig();
		raptorConfig.setUseTimetableUpdates(true);
		this.data = SwissRailRaptorData.create(schedule, null, raptorConfig, scenario.getNetwork(), null);
		this.versions = new TimetableVersions(this.data);
		TimetableUpdateService service = new TimetableUpdateService(this.versions);
		this.response = new Recorder();
		this.stream = service.updateTimetable(this.response);
	}

	@Test
	void snapshotZeroHasItsOwnTimes() {
		send(snapshotZero());
		send(start(0));

		CompletableFuture<VersionedRaptorTimetable> base = this.versions.get(0, 0);
		assertTrue(base.isDone());
		assertEquals(8 * H + 2 * M, boardingAtA(base.join()));
		assertNull(this.response.error);
	}

	@Test
	void requestsWaitForTheirSnapshot() {
		send(snapshotZero());
		send(start(0));
		CompletableFuture<VersionedRaptorTimetable> second = this.versions.get(0, 2);

		send(delta(0, 1, 0, delay1a(7 * M)));
		assertFalse(second.isDone());
		send(delta(0, 2, 0, delay1a(12 * M)));

		assertEquals(8 * H + 12 * M, boardingAtA(second.join()));
		assertEquals(8 * H + 7 * M, boardingAtA(this.versions.get(0, 1).join()));
		assertSame(second.join(), this.versions.get(0, 2).join());
	}

	@Test
	void emptyDeltasKeepTheVersion() {
		send(snapshotZero());
		send(start(0));
		send(delta(0, 1, 0));

		assertSame(this.versions.get(0, 0).join(), this.versions.get(0, 1).join());
	}

	@Test
	void releasedVersionsFail() {
		send(snapshotZero());
		send(start(0));
		send(delta(0, 1, 0, delay1a(7 * M)));
		send(delta(0, 2, 0, delay1a(12 * M)));
		send(delta(0, 3, 2));

		assertTrue(this.versions.get(0, 1).isCompletedExceptionally());
		assertTrue(this.versions.get(0, 0).isCompletedExceptionally());
		assertEquals(8 * H + 12 * M, boardingAtA(this.versions.get(0, 2).join()));
		assertNull(this.response.error);
	}

	@Test
	void iterationsStartOnSnapshotZero() {
		send(snapshotZero());
		send(start(0));
		send(delta(0, 1, 0, delay1a(7 * M)));
		send(delta(0, 2, 0, delay1a(12 * M)));
		CompletableFuture<VersionedRaptorTimetable> neverSent = this.versions.get(0, 5);
		CompletableFuture<VersionedRaptorTimetable> nextIteration = this.versions.get(1, 1);

		send(start(1));

		assertTrue(neverSent.isCompletedExceptionally());
		assertTrue(this.versions.get(0, 2).isCompletedExceptionally());
		assertEquals(8 * H + 2 * M, boardingAtA(this.versions.get(1, 0).join()));
		assertFalse(nextIteration.isDone());

		send(delta(1, 1, 0, delay1a(4 * M)));
		assertEquals(8 * H + 4 * M, boardingAtA(nextIteration.join()));
		assertNull(this.response.error);
	}

	/** Every message that breaks the contract ends the stream and fails the waiting requests. */
	@ParameterizedTest(name = "{0}")
	@MethodSource("violations")
	void violationsEndTheStream(String name, List<TimetableUpdate> messages) {
		CompletableFuture<VersionedRaptorTimetable> waiting = this.versions.get(99, 1);
		for (TimetableUpdate message : messages) {
			send(message);
		}

		assertNotNull(this.response.error, "the stream must end with an error");
		assertEquals(Status.Code.INVALID_ARGUMENT, Status.fromThrowable(this.response.error).getCode());
		assertTrue(waiting.isCompletedExceptionally());
		assertTrue(this.versions.get(0, 0).isCompletedExceptionally());

		// later messages are ignored
		send(start(5));
		this.stream.onCompleted();
		assertFalse(this.response.completed);
	}

	static Stream<Arguments> violations() {
		List<TimetableUpdate> started = new ArrayList<>(snapshotZero());
		started.add(start(0));
		return Stream.of(
			Arguments.of("a gap in the snapshots", with(started, delta(0, 2, 0))),
			Arguments.of("a delta of another iteration", with(started, delta(1, 1, 0))),
			Arguments.of("an iteration that does not follow", with(started, start(2))),
			Arguments.of("an unknown departure", with(started, delta(0, 1, 0, trip(3, 0, new int[]{8 * H}, new int[]{8 * H})))),
			Arguments.of("times that overtake", with(started, delta(0, 1, 0, delay1a(2 * H)))),
			Arguments.of("an unknown route", List.of(base("1", "3", List.of("A", "X", "B")))),
			Arguments.of("other stops", List.of(base("1", "1", List.of("A", "B", "X"), departure("1a", 8 * H, 0, 10 * M, 20 * M)))),
			Arguments.of("a missing route", List.of(snapshotZero().getFirst(), start(0))),
			Arguments.of("a route after the start", with(started, snapshotZero().getFirst())),
			Arguments.of("a delta before the start", with(snapshotZero(), delta(0, 1, 0))),
			Arguments.of("times that are not whole seconds", List.of(update(BaseRoute.newBuilder()
				.setTransitLineId("1").setTransitRouteId("1").addAllStopFacilityIds(List.of("A", "X", "B"))
				.addDepartures(BaseDeparture.newBuilder().setDepartureId("1a")
					.addAllArrivalTimesNs(List.of(ns(8 * H) + 1, ns(8 * H + 10 * M), ns(8 * H + 20 * M)))
					.addAllDepartureTimesNs(List.of(ns(8 * H) + 1, ns(8 * H + 10 * M), ns(8 * H + 20 * M))))
				.build()))),
			Arguments.of("an oldest needed snapshot after the snapshot", with(started, delta(0, 1, 2))),
			Arguments.of("an oldest needed snapshot that decreases", with(with(started, delta(0, 1, 1)), delta(0, 2, 0))),
			Arguments.of("an update without content", List.of(TimetableUpdate.getDefaultInstance()))
		);
	}

	@Test
	void theEndOfTheStreamClosesTheVersions() {
		send(snapshotZero());
		send(start(0));
		CompletableFuture<VersionedRaptorTimetable> waiting = this.versions.get(0, 1);

		this.stream.onCompleted();

		assertTrue(this.response.completed);
		assertEquals(1, this.response.values);
		assertNull(this.response.error);
		assertTrue(waiting.isCompletedExceptionally());
		assertTrue(this.versions.get(0, 0).isCompletedExceptionally());
	}

	@Test
	void aSecondStreamIsRejected() {
		TimetableUpdateService service = new TimetableUpdateService(this.versions);
		service.updateTimetable(new Recorder());
		Recorder second = new Recorder();

		service.updateTimetable(second);

		assertEquals(Status.Code.FAILED_PRECONDITION, Status.fromThrowable(second.error).getCode());
	}

	private void send(List<TimetableUpdate> messages) {
		messages.forEach(this::send);
	}

	private void send(TimetableUpdate message) {
		this.stream.onNext(message);
	}

	/** @return the boarding time at A of a trip from A to B at 7:55 on {@code version} */
	private double boardingAtA(VersionedRaptorTimetable version) {
		SwissRailRaptor raptor = new SwissRailRaptor.Builder(this.data, this.config).with((d, time, person, attributes) -> version).build();
		List<? extends PlanElement> elements = raptor.calcRoute(DefaultRoutingRequest.withoutAttributes(facility(this.a), facility(this.b), 7 * H + 55 * M, null));
		for (PlanElement element : elements) {
			if (element instanceof Leg leg && leg.getRoute() instanceof TransitPassengerRoute route) {
				return route.getBoardingTime().seconds();
			}
		}
		throw new AssertionError("No pt leg from A to B: " + elements);
	}

	/** Snapshot 0 in the order 1a, 1b, 2a; 1a leaves 2 minutes after the schedule. */
	private static List<TimetableUpdate> snapshotZero() {
		return List.of(
			base("1", "1", List.of("A", "X", "B"), departure("1a", 8 * H + 2 * M, 0, 10 * M, 20 * M), departure("1b", 9 * H, 0, 10 * M, 20 * M)),
			base("2", "2", List.of("X", "C"), departure("2a", 8 * H + 30 * M, 0, 10 * M)));
	}

	/** 1a leaves A at 8:00 + {@code delay} and keeps its 10 minutes per hop. */
	private static TripUpdate delay1a(int delay) {
		int start = 8 * H + delay;
		int[] times = {start, start + 10 * M, start + 20 * M};
		return trip(DEP_1A, 0, times, times);
	}

	private static TimetableUpdate base(String line, String route, List<String> stops, BaseDeparture... departures) {
		return update(BaseRoute.newBuilder().setTransitLineId(line).setTransitRouteId(route).addAllStopFacilityIds(stops)
			.addAllDepartures(List.of(departures)).build());
	}

	private static BaseDeparture departure(String id, int start, int... offsets) {
		BaseDeparture.Builder departure = BaseDeparture.newBuilder().setDepartureId(id);
		for (int offset : offsets) {
			departure.addArrivalTimesNs(ns(start + offset)).addDepartureTimesNs(ns(start + offset));
		}
		return departure.build();
	}

	private static TimetableUpdate update(BaseRoute route) {
		return TimetableUpdate.newBuilder().setBaseRoute(route).build();
	}

	private static TimetableUpdate start(int iteration) {
		return TimetableUpdate.newBuilder().setIterationStart(IterationStart.newBuilder().setIteration(iteration)).build();
	}

	private static TimetableUpdate delta(int iteration, int snapshotId, int oldestNeeded, TripUpdate... trips) {
		return TimetableUpdate.newBuilder().setDelta(TimetableDelta.newBuilder().setIteration(iteration).setSnapshotId(snapshotId)
			.setOldestNeededSnapshotId(oldestNeeded).addAllTrips(List.of(trips))).build();
	}

	private static TripUpdate trip(int departure, int fromStop, int[] arrivals, int[] departures) {
		TripUpdate.Builder trip = TripUpdate.newBuilder().setDeparture(departure).setFromStop(fromStop);
		for (int arrival : arrivals) {
			trip.addArrivalTimesNs(ns(arrival));
		}
		for (int departureTime : departures) {
			trip.addDepartureTimesNs(ns(departureTime));
		}
		return trip.build();
	}

	private static List<TimetableUpdate> with(List<TimetableUpdate> messages, TimetableUpdate last) {
		List<TimetableUpdate> all = new ArrayList<>(messages);
		all.add(last);
		return all;
	}

	private static long ns(int seconds) {
		return seconds * RoutingUtils.NANOS_PER_SECOND;
	}

	private static Facility facility(TransitStopFacility stop) {
		return new ActivityFacilitiesFactoryImpl().createActivityFacility(Id.create("at" + stop.getId(), ActivityFacility.class), stop.getCoord(), stop.getLinkId());
	}

	private static TransitStopFacility stop(TransitSchedule schedule, Id<Link> link, String id, double x, double y) {
		TransitStopFacility stop = schedule.getFactory().createTransitStopFacility(Id.create(id, TransitStopFacility.class), new Coord(x, y), false);
		stop.setLinkId(link);
		schedule.addStopFacility(stop);
		return stop;
	}

	/** A route on one line of the same id; {@code departures} alternates departure ids and start times. */
	private static void route(TransitSchedule schedule, TransitScheduleFactory factory, Id<Link> link, String id, List<TransitStopFacility> stops,
							  List<Integer> offsets, Object... departures) {
		List<TransitRouteStop> routeStops = new ArrayList<>();
		for (int i = 0; i < stops.size(); i++) {
			routeStops.add(factory.createTransitRouteStopBuilder(stops.get(i)).arrivalOffset(offsets.get(i)).departureOffset(offsets.get(i)).build());
		}
		TransitRoute route = factory.createTransitRoute(Id.create(id, TransitRoute.class), RouteUtils.createLinkNetworkRouteImpl(link, link), routeStops, "bus");
		for (int i = 0; i < departures.length; i += 2) {
			route.addDeparture(factory.createDeparture(Id.create((String) departures[i], org.matsim.pt.transitSchedule.api.Departure.class), (Integer) departures[i + 1]));
		}
		TransitLine line = factory.createTransitLine(Id.create(id, TransitLine.class));
		line.addRoute(route);
		schedule.addTransitLine(line);
	}

	/** Records what the service answers on the stream. */
	private static final class Recorder implements StreamObserver<Empty> {
		int values = 0;
		Throwable error;
		boolean completed = false;

		@Override
		public void onNext(Empty value) {
			this.values++;
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
