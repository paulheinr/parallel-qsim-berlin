package org.matsim.routing;

/**
 * Constants and time conversions of the router.
 * <p>
 * Times are nanoseconds on the wire (the routing API {@code matsim/services/routing/v1/routing.proto} of matsim-schemas) and seconds in MATSim.
 */
public final class RoutingUtils {

	/** The routing mode the router serves and that its legs carry (the raptor does not set it). */
	public static final String ROUTING_MODE = "pt";

	/** Port the server listens on unless {@code --port} says otherwise. */
	public static final int DEFAULT_PORT = 50051;
	/** Number of routing threads unless {@code --threads} says otherwise. */
	public static final int DEFAULT_THREADS = 1;
	/** Output directory unless {@code --output} says otherwise. */
	public static final String DEFAULT_OUTPUT = "output/router";

	/** How long running requests may take to finish when the server stops, and the worker threads to end. */
	public static final long STOP_TIMEOUT_SECONDS = 10;

	public static final long NANOS_PER_SECOND = 1_000_000_000L;
	public static final int SECONDS_PER_HOUR = 3600;

	private RoutingUtils() {
	}

	/** Nanoseconds on the wire to whole seconds. */
	public static int nsToS(long ns) {
		return (int) (ns / NANOS_PER_SECOND);
	}

	/** Seconds in MATSim to nanoseconds on the wire; the fraction of a second is dropped. */
	public static long sToNs(double s) {
		return (long) s * NANOS_PER_SECOND;
	}

	/**
	 * Nanoseconds on the wire to seconds, for times that must be whole seconds (those of the timetable versions).
	 *
	 * @throws IllegalArgumentException if {@code ns} is not a whole number of seconds, or does not fit into an
	 *                                  {@code int} of seconds; a {@code uint64} above 2^63 arrives as a negative value
	 */
	public static int wholeSeconds(long ns) {
		if (ns < 0 || ns % NANOS_PER_SECOND != 0 || ns / NANOS_PER_SECOND > Integer.MAX_VALUE) {
			throw new IllegalArgumentException("Time " + Long.toUnsignedString(ns) + " ns is not a whole number of seconds between 0 and "
				+ Integer.MAX_VALUE + " s.");
		}
		return (int) (ns / NANOS_PER_SECOND);
	}
}
