JAR := parallel-qsim-berlin-*.jar
BV := v6.4

RUST_BASE := ~/git/parallel_qsim_rust/rust_qsim
RUST_BIN := local_qsim

MEMORY ?= 20G
PCT := 1

java_prepare := java -Xmx$(MEMORY) -XX:+UseParallelGC -cp $(JAR) org.matsim.prepare.RunParallelQSimBerlinPreparation
java_router := java -Xmx$(MEMORY) -XX:+UseParallelGC -cp $(JAR) org.matsim.routing.RoutingServer

p := ./input/$(BV)
op := ./output/$(BV)/$(PCT)pct

.PHONY: prepare

$(JAR):
	mvn clean package -DskipTests

$(op)/berlin-$(BV)-$(PCT)pct.plans-filtered.xml.gz: $(op)/berlin-$(BV)-$(PCT)pct.plans.xml.gz $(JAR)
	$(java_prepare) prepare filter-population\
		--input $<\
		--modes car,walk,ride,bike,freight,truck,pt

$(op)/berlin-$(BV)-$(PCT)pct.plans.xml.gz:
	curl https://svn.vsp.tu-berlin.de/repos/public-svn/matsim/scenarios/countries/de/berlin/berlin-$(BV)/input/$(notdir $@) -o $@

$(op)/berlin-$(BV)-transitSchedule.xml.gz:
	curl https://svn.vsp.tu-berlin.de/repos/public-svn/matsim/scenarios/countries/de/berlin/berlin-$(BV)/input/$(notdir $@) -o $@

$(op)/berlin-$(BV)-vehicleTypes.xml:
	curl https://raw.githubusercontent.com/matsim-scenarios/matsim-berlin/refs/heads/main/input/$(BV)/$(notdir $@) -o $@

$(op)/berlin-$(BV)-vehicleTypes-including-walk-pt.xml: $(op)/berlin-$(BV)-vehicleTypes.xml $(JAR)
	$(java_prepare) prepare adapt-vehicle-types\
		--input $<

$(op)/berlin-$(BV).network.xml.gz:
	curl https://svn.vsp.tu-berlin.de/repos/public-svn/matsim/scenarios/countries/de/berlin/berlin-$(BV)/input/berlin-$(BV)-network-with-pt.xml.gz -o $@

$(op)/berlin-$(BV).config.xml:
	curl https://raw.githubusercontent.com/matsim-scenarios/matsim-berlin/refs/heads/main/input/$(BV)/berlin-$(BV).config.xml -o $@

$(op)/binpb/berlin-$(BV)-$(PCT)pct.ids.binpb: $(op)/berlin-$(BV)-$(PCT)pct.plans-filtered.xml.gz $(op)/berlin-$(BV)-vehicleTypes-including-walk-pt.xml $(op)/berlin-$(BV).network.xml.gz $(op)/berlin-$(BV)-transitSchedule.xml.gz
	cargo flamegraph --bin convert_to_binary --manifest-path $(RUST_BASE)/Cargo.toml --output convert.svg -- \
		--network $(op)/berlin-$(BV).network.xml.gz\
		--population $(op)/berlin-$(BV)-$(PCT)pct.plans-filtered.xml.gz\
		--vehicles $(op)/berlin-$(BV)-vehicleTypes-including-walk-pt.xml\
		--transit-schedule $(op)/berlin-$(BV)-transitSchedule.xml.gz\
		--output-dir $(op)\
		--run-id binpb/berlin-$(BV)-$(PCT)pct

mk-output-folders:
	mkdir -p $(op)/binpb

prepare: mk-output-folders $(op)/binpb/berlin-$(BV)-$(PCT)pct.ids.binpb

run: prepare
	@if [ -n "$(N)" ]; then \
		EXTRA="--set partitioning.num_parts=$(N)"; \
	else \
		EXTRA=""; \
	fi; \
	CMD="cargo flamegraph --example $(RUST_BIN) --manifest-path $(RUST_BASE)/Cargo.toml -- --config-path $p/berlin-v6.4.$(PCT)pct.config.yml $$EXTRA $(ARGS)"; \
	echo "$$CMD"; \
	eval "$$CMD"

run-routing: prepare
	$(MAKE) run RUST_BIN=local_qsim_routing ARGS="--set routing.mode=ad-hoc --router-ip http://localhost:50051"

convert-events:
	cargo --bin proto2xml --release --manifest-path $(RUST_BASE)/Cargo.toml \
		--path $(op)/ \
		--id-store $(op)/binpb/berlin-$(BV)-$(PCT)pct.ids.binpb \
		--num-parts $(N)

convert-network:
	cargo --bin convert_to_xml --release --manifest-path $(RUST_BASE)/Cargo.toml \
		--ids $(op)/binpb/berlin-$(BV)-$(PCT)pct.ids.binpb\
		--network $(op)/berlin-$(BV)-$(PCT)pct.network.$(N).binpb\
		--vehicles $(op)/binpb/berlin-$(BV)-$(PCT)pct.vehicles.binpb

clean:
	rm -rf $(op)

router: $(JAR) $(op)/berlin-$(BV).config.xml
	@if [ -n "$(THREADS)" ]; then \
		EXTRA="--threads $(THREADS)"; \
	else \
		EXTRA=""; \
	fi; \
	$(java_router) --config $(op)/berlin-$(BV).config.xml --sample $(N) --output $(op)/routing $(EXTRA)