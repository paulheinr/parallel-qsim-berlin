package org.matsim.analysis;

import com.google.common.util.concurrent.ListenableFuture;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
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

public class MockRoutingClient {
    public static void main(String[] args) {
        java.nio.file.Path path = java.nio.file.Path.of("requests.pb");

        Map<Integer, java.util.List<routing.Routing.Request>> requests = readRequests(path).stream()
                .collect(Collectors.groupingBy(Routing.Request::getNow));

        ManagedChannel channel = ManagedChannelBuilder.forAddress("localhost", 50051)
                .usePlaintext().build();

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
