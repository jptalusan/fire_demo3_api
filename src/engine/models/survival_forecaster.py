
import numpy as np
class Forecaster:

    def __init__(self):
        self.model_params = None
        self.name = None
        self.model_stats = None

    def fit(self):
        pass

    def predict(self):
        pass

    def get_regression_expr(self):
        pass

    def update_model_stats(self):
        pass

    def get_likelihood(self):
        pass



class SurvivalRegressionForecaster(Forecaster):

    def __init__(self):
        self.name = 'Survival_Regression'
        self.model_params = {}

    def _get_likelihood(self, df, w, features):
        """
        Computes the log-likelihood of the uncensored exponential survival model.
        """
        x = np.array(df[features])
        w_x = np.dot(x, w.T)
        log_t = np.log(df['time_bet']).values.reshape(-1, 1)

        
        # diff = log_t - w_x
        diff=np.clip(log_t - w_x, -500, 500)

        # diff= np.array(diff, dtype=np.float64)
        # print(np.exp(diff))
        #checking i
        likelihood = (diff - np.exp(diff)).sum()
        return likelihood

    def _do_gradient_step(self, df, w, features, alpha=0.01):
        """
        Performs one gradient step for the given parameters.
        """
        x = np.array(df[features])
        w_x = np.dot(x, w.T)
        log_t = np.log(df['time_bet']).values.reshape(-1, 1)
        diff = np.exp(np.clip(log_t - w_x, -500, 500))

        grad = np.zeros_like(w)
        for j in range(len(features)):
            x_j = x[:, j].reshape(-1, 1)
            grad[0, j] = (-x_j + x_j * diff).sum()

        w += alpha * grad
        return w,grad

    def _gradient_descent(self, df, features, tolerance=1e-4, alpha=2e-5, max_iter=100000):
        """
        Runs gradient descent to optimize the model parameters.
        """
        w = np.random.randn(1, len(features)) * 0.01
        l_old = -1e10
        l = self._get_likelihood(df, w, features)
        iteration = 0

        while np.abs(l - l_old) > tolerance and iteration < max_iter:
            print(f"Iteration {iteration}", end="\r")
            w,grad = self._do_gradient_step(df, w, features, alpha)
            
            l_old = l
            l = self._get_likelihood(df, w, features)
            iteration += 1
        # print(f"Iteration {iteration}, Likelihood: {l}, Weights: {w}, Gradients: {grad}")

        return w

    def fit(self, df, metadata):
        """
        Fits the regression model to the data.
        """
        features = metadata['features']
        clusters = df['cluster_label'].unique()
        
        for temp_cluster in clusters:
            df_cluster = df[df['cluster_label'] == temp_cluster]
            w = self._gradient_descent(df_cluster, features)
            self.model_params[temp_cluster] = w.tolist()

        print(f'Finished Learning {self.name} model')

    def predict(self, x_test, metadata):
        """
        Predicts E(y|x) for a set of x, where y is the concerned dependent variable.
        """
        predictions = []
        features = metadata['features']  # Get the list of feature names

        for index, row in x_test.iterrows():
            cluster_label = row['cluster_label']
            if cluster_label in self.model_params:
                w = np.array(self.model_params[cluster_label])
                x = np.array(row[features])  # Use feature names to extract data
                
                # Compute the log prediction
                log_pred = np.dot(x, w.T).item()  # Convert to a scalar if it's an array of size 1
                
                # Compute the exponent of the prediction
                pred_time_bet = np.exp(log_pred)
                predictions.append(pred_time_bet)  # Append the result directly
            else:
                predictions.append(np.nan)  # Return NaN if no model found for the cluster

        x_test['predicted_time_bet'] = predictions
        return x_test



    def sample(self, x_test, metadata):
        """
        Samples time between incidents from the exponential distribution parameterized by the model,
        rather than returning the expected value.
        """
        samples = []
        features = metadata['features']

        for index, row in x_test.iterrows():
            cluster_label = row['cluster_label']
            if cluster_label in self.model_params:
                w = np.array(self.model_params[cluster_label])
                x = np.array(row[features])

                log_pred = np.dot(x, w.T).item()
                scale = np.exp(log_pred)  # E[T] = 1/lambda = exp(w·x)
                samples.append(np.random.exponential(scale))
            else:
                samples.append(np.nan)

        x_test['predicted_time_bet'] = samples
        return x_test

    def get_regression_expr(self):
        """
        Creates regression expression in the form of a patsy expression.
        """
        expressions = []
        for cluster, params in self.model_params.items():
            terms = [f"{coef}*x{i}" for i, coef in enumerate(params[0])]
            expr = " + ".join(terms)
            expressions.append(f"Cluster {cluster}: log(T) ~ {expr}")

        return "\n".join(expressions)
    
    def calculate_incident_rate(self, x_test, metadata):
        """
        Calculates the rate of incidents (lambda) for each test data point.
        """
        rates = []
        features = metadata['features']
        total_incident_rate = 0.0

        for index, row in x_test.iterrows():
            cluster_label = row['cluster_label']
            if cluster_label in self.model_params:
                w = np.array(self.model_params[cluster_label])
                x = np.array(row[features])

                # Compute log prediction
                log_pred = np.dot(x, w.T).item()

                # Compute rate (lambda)
                rate_lambda = np.exp(-log_pred)
                rates.append(rate_lambda)
                total_incident_rate += rate_lambda
            else:
                rates.append(np.nan)

        x_test['incident_rate'] = rates
        return x_test, total_incident_rate

