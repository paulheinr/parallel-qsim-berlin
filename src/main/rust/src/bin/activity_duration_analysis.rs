use rust_qsim::simulation::events::utils::read_proto_events;
use rust_qsim::simulation::events::{
    ActivityEndEvent, ActivityStartEvent, EventsManager, PersonDepartureEvent,
};
use rust_qsim::simulation::id::Id;
use rust_qsim::simulation::logging::init_std_out_logging_thread_local;
use rust_qsim::simulation::population::InternalPerson;
use std::cell::RefCell;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::rc::Rc;

fn main() {
    let _g = init_std_out_logging_thread_local();

    rust_qsim::simulation::id::load_from_file(Path::new(
        "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/binpb-hor600/berlin-v6.4-1pct.ids.binpb",
    ));

    let mut events = EventsManager::new();

    let handler = Rc::new(RefCell::new(MyHandler::default()));
    let handler1 = handler.clone();
    let handler2 = handler.clone();
    let handler3 = handler.clone();

    events.on::<ActivityEndEvent, _>(move |e| {
        handler.borrow_mut().act_end(e);
    });

    events.on::<ActivityStartEvent, _>(move |e| {
        handler1.borrow_mut().act_start(e);
    });

    events.on::<PersonDepartureEvent, _>(move |e| {
        handler2.borrow_mut().departure(e);
    });

    events.on_finish(move || {
        handler3.borrow().write(Path::new(
            "/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/output-12/activities.csv",
        ));
    });

    read_proto_events(
        &mut events,
        &PathBuf::from("/Users/paulh/git/parallel-qsim-berlin/output/v6.4/1pct/output-12"),
        "events".to_string(),
        12,
    );
}

#[derive(Default)]
struct MyHandler {
    act_start_by_person: HashMap<Id<InternalPerson>, u32>,
    act_count: HashMap<Id<InternalPerson>, u32>,
    act_record: HashMap<Id<InternalPerson>, Vec<ActivitySummary>>,
}

impl MyHandler {
    fn act_start(&mut self, event: &ActivityStartEvent) {
        // Increase activity count for the person
        self.act_count
            .entry(event.person.clone())
            .and_modify(|count| *count += 1);

        // Record activity details
        let before = self
            .act_start_by_person
            .insert(event.person.clone(), event.time);
        assert!(before.is_none());
    }

    fn act_end(&mut self, event: &ActivityEndEvent) {
        let start = self.act_start_by_person.remove(&event.person);
        let summary = ActivitySummary {
            act_type: event.act_type.external().to_string(),
            person: event.person.external().to_string(),
            link: event.person.external().to_string(),
            duration: event.time - start.unwrap_or(0),
            count: *self.act_count.entry(event.person.clone()).or_insert(1),
            mode: "".to_string(),
            routing_mode: "".to_string(),
        };
        self.act_record
            .entry(event.person.clone())
            .or_default()
            .push(summary)
    }

    fn departure(&mut self, event: &PersonDepartureEvent) {
        let records = self.act_record.get_mut(&event.person).unwrap_or_else(|| {
            panic!(
                "No activity records found for person {} and event {:?}",
                event.person.external(),
                event
            )
        });

        let last = records.len() - 1;
        let entry = records.get_mut(last).unwrap();

        entry.mode = event.leg_mode.external().to_string();
        entry.routing_mode = event.routing_mode.external().to_string();
    }

    fn write(&self, path: &Path) {
        // write csv of self.act_record to path
        let mut wtr = csv::Writer::from_path(path).expect("Unable to create CSV writer");
        wtr.write_record(&[
            "act_type",
            "person",
            "link",
            "duration",
            "count",
            "mode",
            "routing_mode",
        ])
        .expect("Unable to write header");
        for records in self.act_record.values() {
            for record in records {
                wtr.write_record(&[
                    &record.act_type,
                    &record.person,
                    &record.link,
                    &record.duration.to_string(),
                    &record.count.to_string(),
                    &record.mode,
                    &record.routing_mode,
                ])
                .expect("Unable to write record");
            }
        }
    }
}

struct ActivitySummary {
    act_type: String,
    person: String,
    link: String,
    duration: u32,
    count: u32,
    mode: String,
    routing_mode: String,
}
