package org.matsim.prepare;

import org.matsim.application.MATSimApplication;
import picocli.CommandLine;

@CommandLine.Command(header = ":: ParallelQSimBerlinPreparation ::", version = "1.0", mixinStandardHelpOptions = true)
@MATSimApplication.Prepare({FilterPopulation.class, AdaptVehicleTypes.class})
public class RunParallelQSimBerlinPreparation extends MATSimApplication {
    public static void main(String[] args) {
        MATSimApplication.run(RunParallelQSimBerlinPreparation.class, args);
    }
}
