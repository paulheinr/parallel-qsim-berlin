package org.matsim.analysis;

import com.google.common.util.concurrent.ListenableFuture;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.matsim.application.MATSimAppCommand;
import picocli.CommandLine;
import routing.Routing;
import routing.RoutingServiceGrpc;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class MockRoutingClient implements MATSimAppCommand {
    @CommandLine.Option(names = "--requestsFile", description = "Path to requests file", defaultValue = "requests.pb")
    private String requestsFile;

    @CommandLine.Option(names = "--ip", description = "IP Address of the routing server", defaultValue = "localhost")
    private String ip;

    @CommandLine.Option(names = "--port", description = "Port of the routing server", defaultValue = "50051")
    private int port;

    public static void main(String[] args) {
        new MockRoutingClient().execute(args);
    }

    @Override
    public Integer call() throws Exception {
        Map<Integer, java.util.List<routing.Routing.Request>> requests = readRequests(Path.of(requestsFile)).stream()
                .collect(Collectors.groupingBy(Routing.Request::getNow));

        ManagedChannel channel = ManagedChannelBuilder.forAddress(ip, port).usePlaintext().build();

        RoutingServiceGrpc.RoutingServiceFutureStub service = RoutingServiceGrpc.newFutureStub(channel);

        int now = 0;
        Map<Integer, List<ListenableFuture<Routing.Response>>> openFuturesByDeparture = new java.util.TreeMap<>();

        while (now < 36 * 60 * 60) {
            if (now % 3600 == 0) {
                System.out.println("Processing now = " + now / 3600 + "h");
            }

            List<Routing.Request> currentRequests = requests.getOrDefault(now, List.of());
            for (Routing.Request currentRequest : currentRequests) {
                int dep = currentRequest.getDepartureTime();
                ListenableFuture<Routing.Response> future = service.getRoute(currentRequest);
                openFuturesByDeparture.computeIfAbsent(dep, k -> new LinkedList<>()).add(future);
            }

            // process all open futures for departures up to now
            for (Map.Entry<Integer, List<ListenableFuture<Routing.Response>>> entry : openFuturesByDeparture.entrySet()) {
                if (entry.getKey() <= now) {
                    for (ListenableFuture<Routing.Response> future : entry.getValue()) {
                        try {
                            Routing.Response response = future.get();
                            // process response if needed
                        } catch (Exception e) {
                            throw new RuntimeException(e);
                        }
                    }
                }
            }

            now++;
        }

        return 0;
    }

    private static List<Routing.Request> readRequests(Path path) {
        List<Routing.Request> messages = new ArrayList<>();

        try (InputStream in = Files.newInputStream(path)) {
            Routing.Request msg;
            while ((msg = Routing.Request.parseDelimitedFrom(in)) != null) {
                messages.add(msg);
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }

        return messages;
    }
}
