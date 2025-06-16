package org.matsim;
import com.google.protobuf.CodedInputStream;
import ids.Ids;
import net.jpountz.lz4.LZ4FrameInputStream;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Node;
import org.matsim.api.core.v01.population.Person;
import org.matsim.vehicles.Vehicle;
import org.matsim.vehicles.VehicleType;

import java.io.*;
import java.nio.file.Path;
import java.util.*;

public class IdStoreDeserializer {
    public static final Map<Long, Class> TYPE_ID_TO_CLASS = Map.of(
            1L, String.class,
            2L, Person.class,
            3L, Link.class,
            4L, Node.class,
            5L, VehicleType.class,
            6L, Vehicle.class,
            7L, Integer.class,
            8L, Long.class,
            9L, u32.class,
            10L, Float.class
    );

    // This method reads a file containing serialized Ids.IdsWithType messages.
    // In Rust, all messages are written one after another, with a length prefix for each message.
    public static Map<Long, List<String>> loadIdStore(Path path) {
        Map<Long, List<String>> idStore = new HashMap<>();

        File file = path.toFile();
        try (InputStream input = new FileInputStream(file)) {
            CodedInputStream protoInputStream = CodedInputStream.newInstance(input);

            while (!protoInputStream.isAtEnd()) {
                // This line is important: it reads the length of the next message
                int length = protoInputStream.readRawVarint32();

                // Read the raw bytes of the message based on the length
                byte[] messageBytes = protoInputStream.readRawBytes(length);

                Ids.IdsWithType idsWithType = Ids.IdsWithType.parseFrom(messageBytes);
                long typeId = idsWithType.getTypeId();

                byte[] data;
                if (idsWithType.hasRaw()) {
                    data = idsWithType.getRaw().toByteArray();
                } else if (idsWithType.hasLz4Data()) {
                    data = decompressLz4(idsWithType.getLz4Data().toByteArray());
                } else {
                    continue; // skip if no data
                }

                List<String> externalIds = decodeStringsFromBytes(data);
                idStore.put(typeId, externalIds);
            }
        } catch (IOException e) {
            throw new RuntimeException("Failed to read or parse the id store file: " + path, e);
        }

        return idStore;
    }

    private static byte[] decompressLz4(byte[] compressed) throws IOException {
        try (InputStream in = new LZ4FrameInputStream(new ByteArrayInputStream(compressed));
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            in.transferTo(out);
            return out.toByteArray();
        }
    }

    private static List<String> decodeStringsFromBytes(byte[] bytes) throws IOException {
        List<String> strings = new ArrayList<>();
        CodedInputStream cis = CodedInputStream.newInstance(bytes);

        while (!cis.isAtEnd()) {
            strings.add(cis.readString());
        }

        return strings;
    }

    private static class u32 {}
}