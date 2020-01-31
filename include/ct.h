#ifndef LIBCT_H
#define LIBCT_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct ct_tracker_t ct_tracker;
typedef struct ct_graph_t ct_graph;
typedef struct ct_detection_t ct_detection;
typedef struct ct_conflict_t ct_conflict;

//
// tracker API
//

ct_tracker* ct_tracker_create();
void ct_tracker_destroy(ct_tracker* t);
void ct_tracker_finalize(ct_tracker* t);

ct_graph* ct_tracker_get_graph(ct_tracker* t);
ct_detection* ct_graph_add_detection(ct_graph* g, int timestep, int detection, int number_of_incoming, int number_of_outgoing, int number_of_conflicts);
ct_conflict* ct_graph_add_conflict(ct_graph* g, int timestep, int conflict, int number_of_detections);
ct_detection* ct_graph_get_detection(ct_graph* g, int timestep, int detection);
void ct_graph_add_transition(ct_graph* g, int timestep_from, int detection_from, int index_from, int detection_to, int index_to);
void ct_graph_add_division(ct_graph* g, int timestep_from, int detection_from, int index_from, int detection_to_1, int index_to_1, int detection_to_2, int index_to_2);
void ct_graph_add_conflict_link(ct_graph* g, int timestep, int conflict, int conflict_slot, int detection, int detection_slot);
ct_conflict* ct_graph_get_conflict(ct_graph* g, int timestep, int conflict);

void ct_tracker_run(ct_tracker* t, int max_iterations);
double ct_tracker_lower_bound(ct_tracker* t);
double ct_tracker_evaluate_primal(ct_tracker* t);
void ct_tracker_forward_step(ct_tracker* t, int timestep);
void ct_tracker_backward_step(ct_tracker* t, int timestep);

//
// detection API
//

void ct_detection_set_detection_cost(ct_detection* d, double on);
void ct_detection_set_appearance_cost(ct_detection* d, double c);
void ct_detection_set_disappearance_cost(ct_detection* d, double c);
void ct_detection_set_incoming_cost(ct_detection* d, int idx, double c);
void ct_detection_set_outgoing_cost(ct_detection* d, int idx, double c);

double ct_detection_get_detection_cost(ct_detection* d);
double ct_detection_get_appearance_cost(ct_detection* d);
double ct_detection_get_disappearance_cost(ct_detection* d);
double ct_detection_get_incoming_cost(ct_detection* d, int idx);
double ct_detection_get_outgoing_cost(ct_detection* d, int idx);

int ct_detection_get_incoming_primal(ct_detection* d);
int ct_detection_get_outgoing_primal(ct_detection* d);

//
// conflict API
//

void ct_conflict_set_cost(ct_conflict* c, int idx, double cost);
double ct_conflict_get_cost(ct_conflict* c, int idx);
int ct_conflict_get_primal(ct_conflict* c);

#ifdef __cplusplus
}
#endif

#endif

/* vim: set ts=8 sts=2 sw=2 et ft=c: */
