import re

from .model import Model


class TxtBase:

    def __repr__(self):
        args = ['{}={!r}'.format(x, self.__dict__[x]) for x in sorted(self.__dict__.keys())]
        return '{}({})'.format(self.__class__.__name__, ', '.join(args))

    def _yes(self):
        return True

    def _no(self):
        return False

    is_variable = _no
    is_detection = _no
    is_disappearance = _no
    is_appearance = _no
    is_disappearance = _no
    is_move = _no
    is_division = _no
    is_conf_set = _no

    def is_transition(self):
        return self.is_move() or self.is_division()


class TxtVariable(TxtBase):

    is_variable = TxtBase._yes

    def __init__(self, unique_id, cost):
        self.unique_id = unique_id
        self.cost = cost


class TxtDetection(TxtVariable):

    is_detection = TxtVariable._yes

    def __init__(self, timestep, unique_id, cost):
        super().__init__(unique_id, cost)
        self.timestep = timestep


class TxtAppearance(TxtVariable):

    is_appearance = TxtVariable._yes

    def __init__(self, unique_id, detection_id, cost):
        super().__init__(unique_id, cost)
        self.detection_id = detection_id


class TxtDisappearance(TxtVariable):

    is_disappearance = TxtVariable._yes

    def __init__(self, unique_id, detection_id, cost):
        super().__init__(unique_id, cost)
        self.detection_id = detection_id


class TxtMove(TxtVariable):

    def __init__(self, unique_id, id_from, id_to, cost):
        super().__init__(unique_id, cost)
        self.id_from = id_from
        self.id_to = id_to

    is_move = TxtVariable._yes


class TxtDivision(TxtVariable):

    def __init__(self, unique_id, id_from, id_to_1, id_to_2, cost):
        super().__init__(unique_id, cost)
        self.id_from = id_from
        self.id_to_1 = id_to_1
        self.id_to_2 = id_to_2

    is_division = TxtVariable._yes


class TxtConfSet(TxtBase):

    def __init__(self, detections):
        self.detections = detections

    is_conf_set = TxtBase._yes


def parse_txt_model(f):
    re_comment = re.compile(r'^#|^$')
    re_hypothesis = re.compile(r'^H +([0-9]+) +([0-9]+) +([-.0-9]+)')
    re_app = re.compile(r'^(DIS)?APP +([0-9]+) +([0-9]+) +([-.0-9]+)')
    re_move = re.compile(r'^MOVE +([0-9]+) +([0-9]+) +([0-9]+) +([-.0-9]+)')
    re_div = re.compile(r'^DIV +([0-9]+) +([0-9]+) +([0-9]+) +([0-9]+) +([-.0-9]+)')
    re_confset = re.compile(r'^CONFSET +(.+) +<= 1$')

    for line in f:
        line = line.rstrip('\r\n')

        m = re_comment.search(line)
        if m:
            continue

        m = re_hypothesis.search(line)
        if m:
            yield TxtDetection(
                    timestep=int(m.group(1)),
                    unique_id=int(m.group(2)),
                    cost=float(m.group(3)))
            continue

        m = re_app.search(line)
        if m:
            ctor = TxtDisappearance if m.group(1) == 'DIS' else TxtAppearance
            yield ctor(
                    unique_id=int(m.group(2)),
                    detection_id=int(m.group(3)),
                    cost=float(m.group(4)))
            continue

        m = re_move.search(line)
        if m:
            yield TxtMove(
                    unique_id=int(m.group(1)),
                    id_from=int(m.group(2)),
                    id_to=int(m.group(3)),
                    cost=float(m.group(4)))
            continue

        m = re_div.search(line)
        if m:
            yield TxtDivision(
                    unique_id=int(m.group(1)),
                    id_from=int(m.group(2)),
                    id_to_1=int(m.group(3)),
                    id_to_2=int(m.group(4)),
                    cost=float(m.group(5)))
            continue

        m = re_confset.search(line)
        if m:
            detections = [int(x) for x in re.split(r' *\+ *', m.group(1))]
            yield TxtConfSet(detections=detections)
            continue

        raise RuntimeError('Unhandled input line: {}'.format(line))


def convert_txt_to_ct(txt_model):
    m = Model()
    model_to_id = {}
    id_to_model = {}

    def update_bimap(model_key, id_key):
        #assert model_key not in model_to_id
        #assert id_key not in id_to_model
        model_to_id[model_key] = id_key
        id_to_model[id_key] = model_key

    for item in txt_model:
        if item.is_detection():
            r = m.add_detection(item.timestep, detection=item.cost)
            update_bimap(('H', item.timestep, r), ('H', item.unique_id))
        elif item.is_appearance():
            tag, timestep, detection = id_to_model['H', item.detection_id]
            assert(tag == 'H')

            m.set_detection_cost(timestep, detection, appearance=item.cost)
            update_bimap(('APP', timestep, detection), ('A', item.unique_id))
        elif item.is_disappearance():
            tag, timestep, detection = id_to_model['H', item.detection_id]
            assert(tag == 'H')

            m.set_detection_cost(timestep, detection, disappearance=item.cost)
            update_bimap(('DISAPP', timestep, detection), ('A', item.unique_id))
        elif item.is_move():
            tag_from, timestep_from, detection_from = id_to_model['H', item.id_from]
            assert(tag_from == 'H')

            tag_to, timestep_to, detection_to = id_to_model['H', item.id_to]
            assert(tag_to == 'H')
            assert(timestep_from + 1 == timestep_to)

            m.add_transition(timestep_from, detection_from, detection_to, item.cost)
            update_bimap(('MOVE', timestep_from, detection_from, detection_to), ('A', item.unique_id))
        elif item.is_division():
            tag_from, timestep_from, detection_from = id_to_model['H', item.id_from]
            assert(tag_from == 'H')

            tag_to_1, timestep_to_1, detection_to_1 = id_to_model['H', item.id_to_1]
            assert(tag_to_1 == 'H')
            assert(timestep_from + 1 == timestep_to_1)

            tag_to_2, timestep_to_2, detection_to_2 = id_to_model['H', item.id_to_2]
            assert(tag_to_2 == 'H')
            assert(timestep_from + 1 == timestep_to_2)

            m.add_division(timestep_from, detection_from, detection_to_1, detection_to_2, item.cost)
            update_bimap(('DIV', timestep_from, detection_from, detection_to_1, detection_to_2), ('A', item.unique_id))
        elif item.is_conf_set():
            detections = [id_to_model['H', x] for x in item.detections]
            timestep = detections[0][1]
            assert(all(x[0] == 'H' for x in detections))
            assert(all(x[1] == detections[0][1] for x in detections)) # check that timesteps are all identical
            detections = [x[2] for x in detections]
            m.add_conflict(timestep, detections)
        else:
            assert(False)

    return m, (model_to_id, id_to_model)


def format_txt_primals(primals, bimaps, out):
    assert primals.check_consistency()
    model_to_id, id_to_model = bimaps

    def unique_id(*args):
        tag, unique_id = model_to_id[args]
        assert tag == 'H' if args[0] == 'H' else 'A'
        return unique_id

    for timestep, detection in primals._detections:
        if primals.appearance(timestep, detection):
            out.write('APP {}\n'.format(unique_id('APP', timestep, detection)))
        out.write('H {}\n'.format(unique_id('H', timestep, detection)))
        if primals.disappearance(timestep, detection):
            out.write('DISAPP {}\n'.format(unique_id('DISAPP', timestep, detection)))

    for timestep, detection_left, detection_right in primals._transitions:
        out.write('MOVE {}\n'.format(unique_id('MOVE', timestep, detection_left, detection_right)))

    for timestep, detection_left, detection_right_1, detection_right_2 in primals._divisions:
        out.write('DIV {}\n'.format(unique_id('DIV', timestep, detection_left, detection_right_1, detection_right_2)))
