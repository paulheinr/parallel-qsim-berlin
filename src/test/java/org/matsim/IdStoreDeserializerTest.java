package org.matsim;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
class IdStoreDeserializerTest {

    @Test
    void testDeserialize() {
        Path idStorePath = Path.of("src/test/resources/org/matsim/ids.pbf");

        Map<Long, List<String>> longListMap = IdStoreDeserializer.loadIdStore(idStorePath);

        assertNotNull(longListMap);
        assertFalse(longListMap.isEmpty(), "Id store should not be empty");

        assertEquals(longListMap.get(0L), List.of("test-1", "test-2"));
        assertEquals(longListMap.get(1L), List.of("string-id"));
    }
}