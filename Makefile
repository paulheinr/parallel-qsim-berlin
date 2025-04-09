JAR := parallel-qsim-berlin-*.jar
BV := v6.4

RUST_BASE := ~/git/parallel_qsim_rust
RUST_EXE := $(RUST_BASE)/target/release

MEMORY ?= 20G
PCT := 10

java := java -Xmx$(MEMORY) -XX:+UseParallelGC -cp $(JAR) org.matsim.prepare.RunParallelQSimBerlinPreparation

p := input/$(BV)
op := output/$(BV)

.PHONY: prepare

$(JAR):
	mvn package

$(RUST_EXE):
	cd $(RUST_BASE) && cargo build --release

$(op)/berlin-$(BV)-$(PCT)pct.plans-filtered.xml.gz: $(op)/berlin-$(BV)-$(PCT)pct.plans.xml.gz
	$(java) prepare filter-population\
		--input $<\
		--modes car,walk,ride,bike,freight,truck\

$(op)/berlin-$(BV)-$(PCT)pct.plans.xml.gz:
	curl https://svn.vsp.tu-berlin.de/repos/public-svn/matsim/scenarios/countries/de/berlin/berlin-$(BV)/input/$(notdir $@) -o $@

$(op)/berlin-$(BV)-vehicleTypes.xml:
	curl https://raw.githubusercontent.com/matsim-scenarios/matsim-berlin/refs/heads/main/input/$(BV)/$(notdir $@) -o $@

$(op)/berlin-$(BV)-vehicleTypes-including-walk.xml: $(op)/berlin-$(BV)-vehicleTypes.xml
	$(java) prepare adapt-vehicle-types\
		--input $<\
		--teleported-modes bike,walk,ride\

$(op)/berlin-$(BV).network.xml.gz:
	curl https://svn.vsp.tu-berlin.de/repos/public-svn/matsim/scenarios/countries/de/berlin/berlin-$(BV)/input/berlin-$(BV)-network-with-pt.xml.gz -o $@

$(op)/binpb/berlin-$(BV)-$(PCT)pct.ids.binpb: $(op)/berlin-$(BV)-$(PCT)pct.plans-filtered.xml.gz $(op)/berlin-$(BV)-vehicleTypes-including-walk.xml $(op)/berlin-$(BV).network.xml.gz
	$(RUST_EXE)/convert_to_binary\
		--network $(op)/berlin-$(BV).network.xml.gz\
		--population $(op)/berlin-$(BV)-$(PCT)pct.plans-filtered.xml.gz\
		--vehicles $(op)/berlin-$(BV)-vehicleTypes-including-walk.xml\
		--output-dir $(op)\
		--run-id binpb/berlin-$(BV)-$(PCT)pct\

prepare: $(op)/binpb/berlin-$(BV)-$(PCT)pct.ids.binpb

run: $(op)/binpb/berlin-$(BV)-$(PCT)pct.ids.binpb
	$(RUST_EXE)/local_qsim --config-path $p/berlin-v6.4.config.yml