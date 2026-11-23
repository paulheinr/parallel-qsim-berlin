package org.matsim.routing;

import ch.sbb.matsim.routing.pt.raptor.*;
import org.matsim.api.core.v01.population.Person;
import org.matsim.utils.objectattributes.attributable.Attributes;

/**
 * Lets each request route on the timetable version that {@link RoutingService} has waited for and put into its routing
 * attributes under {@link #ATTRIBUTE}. Requests without it route on the transit schedule.
 * <p>
 * The routing attributes are the only input per request that reaches the provider, which all router threads share.
 * It neither waits nor looks anything up, so it is cheap and thread-safe.
 */
final class RequestTimetableProvider implements RaptorTimetableProvider {

    /**
     * The routing attribute with the {@link VersionedRaptorTimetable} of a request.
     */
    static final String ATTRIBUTE = "timetableVersion";

    private final RaptorTimetableProvider defaultSchedule = new DefaultRaptorTimetableProvider();

    @Override
    public RaptorTimetable getTimetable(SwissRailRaptorData data, double departureTime, Person person, Attributes routingAttributes) {
        // RoutingService puts the version it waited for under ATTRIBUTE. Requests without a version have no entry, and
        // callers without routing attributes (e.g. SwissRailRaptor.calcTree from stops) pass null.
        Object version = routingAttributes == null ? null : routingAttributes.getAttribute(ATTRIBUTE);
        if (version == null) {
            return this.defaultSchedule.getTimetable(data, departureTime, person, routingAttributes);
        }
        if (version instanceof VersionedRaptorTimetable timetable) {
            return timetable;
        }
        throw new IllegalArgumentException("The routing attribute " + ATTRIBUTE + " must be a VersionedRaptorTimetable, but is a "
                + version.getClass().getName() + ".");
    }
}
