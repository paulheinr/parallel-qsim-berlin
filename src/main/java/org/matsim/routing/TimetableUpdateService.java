package org.matsim.routing;

import com.google.protobuf.Empty;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.schemas.services.routing.v1.TimetableServiceGrpc;
import org.matsim.schemas.services.routing.v1.TimetableUpdate;

import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Receives the timetable stream of the simulation (see {@code TimetableService} in
 * {@code matsim/services/routing/v1/routing.proto} of matsim-schemas) and builds the versions in
 * {@link TimetableVersions}.
 * <p>
 * The router accepts one stream for its lifetime. A message that breaks the contract ends the stream with
 * {@code INVALID_ARGUMENT}, and the versions are closed, so that waiting and later requests fail; the simulation then
 * has to abort the run.
 */
final class TimetableUpdateService extends TimetableServiceGrpc.TimetableServiceImplBase {
	private static final Logger log = LogManager.getLogger(TimetableUpdateService.class);

	private final TimetableVersions versions;
	private final AtomicBoolean streamOpened = new AtomicBoolean();

	TimetableUpdateService(TimetableVersions versions) {
		this.versions = versions;
	}

	@Override
	public StreamObserver<TimetableUpdate> updateTimetable(StreamObserver<Empty> responseObserver) {
		if (!this.streamOpened.compareAndSet(false, true)) {
			log.error("Rejected a second timetable stream");
			responseObserver.onError(Status.FAILED_PRECONDITION.withDescription("The router accepts only one timetable stream.").asRuntimeException());
			return new IgnoringObserver();
		}
		log.info("Timetable stream opened");
		return new StreamObserver<>() {
			/** set once the stream was ended because of a broken contract; later messages are ignored */
			private boolean failed = false;

			@Override
			public void onNext(TimetableUpdate update) {
				if (this.failed) {
					return;
				}
				try {
					switch (update.getUpdateCase()) {
						case BASE_ROUTE -> versions.addBaseRoute(update.getBaseRoute());
						case ITERATION_START -> versions.startIteration(update.getIterationStart().getIteration());
						case DELTA -> versions.applyDelta(update.getDelta());
						case UPDATE_NOT_SET -> throw new IllegalArgumentException("A timetable update without content.");
					}
				} catch (IllegalArgumentException | IllegalStateException e) {
					fail(Status.INVALID_ARGUMENT, "The timetable stream breaks the contract: " + e.getMessage(), e);
				} catch (RuntimeException e) {
					fail(Status.INTERNAL, "The timetable update failed: " + e, e);
				}
			}

			private void fail(Status status, String message, RuntimeException cause) {
				this.failed = true;
				log.error(message, cause);
				versions.close(new IllegalStateException(message, cause));
				responseObserver.onError(status.withDescription(message).withCause(cause).asRuntimeException());
			}

			@Override
			public void onError(Throwable t) {
				log.error("The timetable stream was aborted", t);
				versions.close(new IllegalStateException("The timetable stream was aborted: " + t, t));
			}

			@Override
			public void onCompleted() {
				if (this.failed) {
					return;
				}
				log.info("Timetable stream ended");
				versions.close(new IllegalStateException("The timetable stream has ended."));
				responseObserver.onNext(Empty.getDefaultInstance());
				responseObserver.onCompleted();
			}
		};
	}

	/** The observer of a rejected stream. */
	private static final class IgnoringObserver implements StreamObserver<TimetableUpdate> {
		@Override
		public void onNext(TimetableUpdate value) {
		}

		@Override
		public void onError(Throwable t) {
		}

		@Override
		public void onCompleted() {
		}
	}
}
