package org.matsim.analysis;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.core.network.NetworkUtils;
import routing.Routing;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class RequestConverter {
    public static void main(String[] args) {
        Network network = NetworkUtils.readNetwork("/Users/paulh/git/parallel-qsim-berlin/output/v6.4/10pct/berlin-v6.4-network-with-pt.xml.gz");

        String csvFile = "/Users/paulh/hlrn-cluster/rust-pt-routing/parallel-qsim-berlin/output/v6.4/10pct/routing-sim192_hor600_w4_r64_10pct/routing-profiling-2025-12-16_23-31-10.csv";

        try (java.io.BufferedReader reader = java.nio.file.Files.newBufferedReader(java.nio.file.Paths.get(csvFile));
             CSVParser csv = new CSVParser(reader, CSVFormat.DEFAULT.builder().setSkipHeaderRecord(true).build());
             OutputStream outputStream = Files.newOutputStream(Path.of("requests.pb"))) {
            csv.stream().skip(1).forEachOrdered(strings -> {
                String now = strings.get(1);
                String departureTime = strings.get(2);
                String from = strings.get(3);
                String to = strings.get(4);
                Entry entry = new Entry(Integer.parseInt(now), Integer.parseInt(departureTime), Id.createLinkId(from), Id.createLinkId(to));

                Routing.Request request = Routing.Request.newBuilder()
                        .setMode("pt")
                        .setFromLinkId(entry.from().toString())
                        .setToLinkId(entry.to().toString())
                        .setFromX(network.getLinks().get(entry.from()).getCoord().getX())
                        .setFromY(network.getLinks().get(entry.from()).getCoord().getY())
                        .setToX(network.getLinks().get(entry.to()).getCoord().getX())
                        .setToY(network.getLinks().get(entry.to()).getCoord().getY())
                        .setDepartureTime(entry.departureTime())
                        .setNow(entry.now())
                        .build();
                try {
                    request.writeDelimitedTo(outputStream);
                } catch (IOException e) {
                    throw new RuntimeException(e);
                }
            });
        } catch (java.io.IOException e) {
            throw new RuntimeException(e);
        }
    }

    record Entry(int now, int departureTime, Id<Link> from, Id<Link> to) {
    }
}

