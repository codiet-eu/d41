from codietpgm.learners.BayesianNetworkLearner import BayesianNetworkLearner
from codietpgm.io.variableannotation import Type
import gurobipy as gp
from gurobipy import GRB


class MILPBN(BayesianNetworkLearner):
    """
    New method proposed in the draft.
    """

    def __init__(self):
        super().__init__(True)
        self.variables = None
        self._model = None
        self.adjacency = None

    def learn_weights(self, data, lambda_wp=0.5, lamda_wm=0.5, lamda_ap=0.5, lamda_am=0.5, b_w=0.1, b_a=0.1):
        super().learn_weights(data)

        # make sure we have dataframe with only continous static features
        data = data.project(data.variables_for_annotation(Type.CONTINUOUS))
        df = data.dynamic_variables()

        T, d = df[0].shape  # n=data samples num, d=num. fetures
        M = len(df)
        x = [dfi.to_numpy() for dfi in df]  # indexing x[sample][time, feature]

        # create gurobi model
        model = gp.Model("MILPDBN")

        # include variables
        ewp = model.addMVar((d, d), vtype=GRB.BINARY, name="EW+")
        ewm = model.addMVar((d, d), vtype=GRB.BINARY, name="EW-")
        eap = model.addMVar((d, d), vtype=GRB.BINARY, name="EA+")
        eam = model.addMVar((d, d), vtype=GRB.BINARY, name="EA-")
        wp = model.addMVar((d, d), lb=b_w, vtype=GRB.CONTINUOUS, name="W+")
        wm = model.addMVar((d, d), ub=-b_w, vtype=GRB.CONTINUOUS, name="W-")
        ap = model.addMVar((d, d), lb=b_a, vtype=GRB.CONTINUOUS, name="A+")
        am = model.addMVar((d, d), ub=-b_a, vtype=GRB.CONTINUOUS, name="A-")

        # helper variables, so that the contraint is quadratic
        hwp = model.addMVar((d, d), vtype=GRB.CONTINUOUS, name="helpwerW+")
        hwm = model.addMVar((d, d), vtype=GRB.CONTINUOUS, name="helpwerW-")
        hap = model.addMVar((d, d), vtype=GRB.CONTINUOUS, name="helpwerA+")
        ham = model.addMVar((d, d), vtype=GRB.CONTINUOUS, name="helpwerA-")

        # helper variables for the criterion
        critvar = model.addMVar((M, T, d), vtype=GRB.CONTINUOUS, name="criterion helper variable" )

        # constraints
        # E_W+ + E_W- <= 1, and E_A+ + E_A- <= 1
        model.addConstrs((ewp[j, k] + ewm[j, k] <= 1 for j in range(d) for k in range(d)), name="E_W+ + E_W- <= 1")
        model.addConstrs((eap[j, k] + eam[j, k] <= 1 for j in range(d) for k in range(d)), name="E_A+ + E_A- <= 1")

        model.addConstrs((wp[j, k] * (1 - ewp[j, k]) == 0 for j in range(d) for k in range(d)), name="W+ (1-E_W+) = 0")
        model.addConstrs((wm[j, k] * (1 - ewm[j, k]) == 0 for j in range(d) for k in range(d)), name="W- (1-E_W-) = 0")
        model.addConstrs((ap[j, k] * (1 - eap[j, k]) == 0 for j in range(d) for k in range(d)), name="A+ (1-E_A+) = 0")
        model.addConstrs((am[j, k] * (1 - eam[j, k]) == 0 for j in range(d) for k in range(d)), name="A- (1-E_A-) = 0")

        # todo DAG constraints

        # helper variables constraints
        model.addConstrs((ewp[j, k] * wp[j, k] == hwp[j, k] for j in range(d) for k in range(d)),
                         name="helper constraint on E_W+ and W+")
        model.addConstrs((ewm[j, k] * wm[j, k] == hwm[j, k] for j in range(d) for k in range(d)),
                         name="helper constraint on E_W- and W-")
        model.addConstrs((eap[j, k] * ap[j, k] == hap[j, k] for j in range(d) for k in range(d)),
                         name="helper constraint on E_A+ and A+")
        model.addConstrs((eam[j, k] * am[j, k] == ham[j, k] for j in range(d) for k in range(d)),
                         name="helper constraint on E_A- and A-")

        # criterion variable helper contraint
        model.addConstrs((critvar[m, t, i] == x[m][t, i]
                          - sum(x[m][t, j] * hwp[j, i] for j in range(d))
                          - sum(x[m][t, j] * hwm[j, i] for j in range(d))
                          # TODO terms with n? - so far coded as n = d ? Also, t - 1 will cause an error, as this is undefined ...
                          - sum(x[m][t - 1, j] * hap[j, i] for j in range(d))
                          - sum(x[m][t - 1, j] * ham[j, i] for j in range(d))
                                           for m in range(M) for t in range(T) for i in range(d)), name="criterion helper variable")


        # define the objective function
        model.setObjective(
            sum((critvar[m, t, i] * critvar[m, t, i]) for m in range(M) for t in range(T) for i in range(d)) +
                # regularization
                lambda_wp * ewp.sum() + lamda_wm * ewm.sum() + lamda_ap * eap.sum() + lamda_am * eam.sum()
            ,
            GRB.MINIMIZE)

        model.optimize()

        self._model = model
        self.variables = df.keys()

    def get_edges(self):
        edge_list = set()
        for i in range(len(self.variables)):
            for j in range(len(self.variables)):
                if int(self.adjacency[i, j].item().X) == 1:  # TODO maybe a better conversion will be needed ...
                    edge_list.add((self.variables[i], self.variables[j]))
        return edge_list