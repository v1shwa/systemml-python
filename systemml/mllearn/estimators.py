#-------------------------------------------------------------
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
#-------------------------------------------------------------

__all__ = ['LinearRegression', 'LogisticRegression', 'SVM', 'NaiveBayes', 'Caffe2DML', 'Keras2DML']

import numpy as np
from pyspark.ml import Estimator
from pyspark.ml.feature import VectorAssembler
from pyspark.sql import DataFrame
import sklearn as sk
from sklearn.metrics import accuracy_score, r2_score
from py4j.protocol import Py4JError
import traceback
from sklearn.preprocessing import LabelEncoder
import threading
import time
import math

from ..converters import *
from ..classloader import *

def assemble(sparkSession, pdf, inputCols, outputCol):
    tmpDF = sparkSession.createDataFrame(pdf, list(pdf.columns))
    assembler = VectorAssembler(inputCols=list(inputCols), outputCol=outputCol)
    return assembler.transform(tmpDF)

class BaseSystemMLEstimator(Estimator):
    features_col = 'features'
    label_col = 'label'
    
    def set_features_col(self, colName):
        """
        Sets the default column name for features of PySpark DataFrame.

        Parameters
        ----------
        colName: column name for features (default: 'features')
        """
        self.features_col = colName

    def set_label_col(self, colName):
        """
        Sets the default column name for features of PySpark DataFrame.

        Parameters
        ----------
        colName: column name for features (default: 'label')
        """
        self.label_col = colName

    def setGPU(self, enable):
        """
        Whether or not to enable GPU.

        Parameters
        ----------
        enable: boolean
        """
        self.estimator.setGPU(enable)
        return self
    
    def setForceGPU(self, enable):
        """
        Whether or not to force the usage of GPU operators.

        Parameters
        ----------
        enable: boolean
        """
        self.estimator.setForceGPU(enable)
        return self
        
    def setExplain(self, explain):
        """
        Explanation about the program. Mainly intended for developers.

        Parameters
        ----------
        explain: boolean
        """
        self.estimator.setExplain(explain)
        return self
    
    def setExplainLevel(self, explainLevel):
        """
        Set explain level. Mainly intended for developers.
        
        Parameters
        ----------
        explainLevel: string
            Can be one of "hops", "runtime", "recompile_hops", "recompile_runtime"
            or in the above in upper case.
        """
        self.estimator.setExplainLevel(explainLevel)
        return self
            
    def setStatistics(self, statistics):
        """
        Whether or not to output statistics (such as execution time, elapsed time)
        about script executions.

        Parameters
        ----------
        statistics: boolean
        """
        self.estimator.setStatistics(statistics)
        return self
    
    def setStatisticsMaxHeavyHitters(self, maxHeavyHitters):
        """
        The maximum number of heavy hitters that are printed as part of the statistics.

        Parameters
        ----------
        maxHeavyHitters: int
        """
        self.estimator.setStatisticsMaxHeavyHitters(maxHeavyHitters)
        return self
        
    def setConfigProperty(self, propertyName, propertyValue):
        """
        Set configuration property, such as setConfigProperty("sysml.localtmpdir", "/tmp/systemml").

        Parameters
        ----------
        propertyName: String
        propertyValue: String
        """
        self.estimator.setConfigProperty(propertyName, propertyValue)
        return self
    
    def _fit_df(self):
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        try:
            if default_jvm_stdout:
                with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                    self.model = self.estimator.fit(self.X._jdf)
            else:
                self.model = self.estimator.fit(self.X._jdf)
        except Py4JError:
            traceback.print_exc()
    
    def fit_df(self, X):
        self.X = X
        self._fit_df()
        self.X = None
        return self
    
    def _fit_numpy(self):
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        try:
            if type(self.y) == np.ndarray and len(self.y.shape) == 1:
                # Since we know that mllearn always needs a column vector
                self.y = np.matrix(self.y).T
            y_mb = convertToMatrixBlock(self.sc, self.y)
            if default_jvm_stdout:
                with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                    self.model = self.estimator.fit(convertToMatrixBlock(self.sc, self.X), y_mb)
            else:
                self.model = self.estimator.fit(convertToMatrixBlock(self.sc, self.X), y_mb)
        except Py4JError:
            traceback.print_exc()
                    
    def fit_numpy(self, X, y):
        self.X = X
        self.y = y
        self._fit_numpy()
        self.X = None
        self.y = None
        return self

    def fit_file(self, X_file, y_file):
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        try:
            if default_jvm_stdout:
                with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                    self.model = self.estimator.fit(X_file, y_file)
            else:
                self.model = self.estimator.fit(X_file, y_file)
        except Py4JError:
            traceback.print_exc()
        return self
                
    # Returns a model after calling fit(df) on Estimator object on JVM
    def _fit(self, X):
        """
        Invokes the fit method on Estimator object on JVM if X is PySpark DataFrame

        Parameters
        ----------
        X: PySpark DataFrame that contain the columns features_col (default: 'features') and label_col (default: 'label')
        """
        if hasattr(X, '_jdf') and self.features_col in X.columns and self.label_col in X.columns:
            return self.fit_df(X)
        else:
            raise Exception('Incorrect usage: Expected dataframe as input with features/label as columns')

    def fit(self, X, y=None, params=None):
        """
        Invokes the fit method on Estimator object on JVM if X and y are on of the supported data types

        Parameters
        ----------
        X: NumPy ndarray, Pandas DataFrame, scipy sparse matrix, Spark DataFrame, file path
        y: NumPy ndarray, Pandas DataFrame, scipy sparse matrix, file path
        """
        if y is None:
            return self._fit(X)
        elif isinstance(X, str) and isinstance(y, str):
            return self.fit_file(X, y)
        elif isinstance(X, SUPPORTED_TYPES) and isinstance(y, SUPPORTED_TYPES):
            # Donot encode if y is a numpy matrix => useful for segmentation
            skipEncodingY = len(y.shape) == 2 and y.shape[0] != 1 and y.shape[1] != 1
            y = y if skipEncodingY else self.encode(y)
            if self.transferUsingDF:
                pdfX = convertToPandasDF(X)
                pdfY = convertToPandasDF(y)
                if getNumCols(pdfY) != 1 and not skipEncodingY:
                    raise Exception('y should be a column vector')
                if pdfX.shape[0] != pdfY.shape[0]:
                    raise Exception('Number of rows of X and y should match')
                colNames = pdfX.columns
                pdfX[self.label_col] = pdfY[pdfY.columns[0]]
                df = assemble(self.sparkSession, pdfX, colNames, self.features_col).select(self.features_col, self.label_col)
                self.fit_df(df)
            else:
                numColsy = getNumCols(y)
                if numColsy != 1 and not skipEncodingY:
                    raise Exception('Expected y to be a column vector')
                self.fit_numpy(X, y)
            if self.setOutputRawPredictionsToFalse:
                self.model.setOutputRawPredictions(False)
            return self
        else:
            raise Exception('Unsupported input type')

    def transform(self, X):
        return self.predict(X)
    
    def _convertPythonXToJavaObject(self, X):
        """
        Converts the input python object X to a java-side object (either MatrixBlock or Java DataFrame)

        Parameters
        ----------
        X: NumPy ndarray, Pandas DataFrame, scipy sparse matrix or PySpark DataFrame
        """
        if isinstance(X, SUPPORTED_TYPES) and self.transferUsingDF:
            pdfX = convertToPandasDF(X)
            df = assemble(self.sparkSession, pdfX, pdfX.columns, self.features_col).select(self.features_col)
            return df._jdf
        elif isinstance(X, SUPPORTED_TYPES):
            return convertToMatrixBlock(self.sc, X)
        elif hasattr(X, '_jdf') and self.features_col in X.columns:
            # No need to assemble as input DF is likely coming via MLPipeline
            return X._jdf
        elif hasattr(X, '_jdf'):
            assembler = VectorAssembler(inputCols=X.columns, outputCol=self.features_col)
            df = assembler.transform(X)
            return df._jdf
        else:
            raise Exception('Unsupported input type')
        
    def _convertJavaOutputToPythonObject(self, X, output):
        """
        Converts the a java-side object output (either MatrixBlock or Java DataFrame) to a python object (based on the type of X).

        Parameters
        ----------
        X: NumPy ndarray, Pandas DataFrame, scipy sparse matrix or PySpark DataFrame
        output: a java-side object (either MatrixBlock or Java DataFrame)
        """
        if isinstance(X, SUPPORTED_TYPES) and self.transferUsingDF:
            retDF = DataFrame(output, self.sparkSession)
            retPDF = retDF.sort('__INDEX').select('prediction').toPandas()
            return retPDF.as_matrix().flatten() if isinstance(X, np.ndarray) else retPDF
        elif isinstance(X, SUPPORTED_TYPES):
            return convertToNumPyArr(self.sc, output)
        elif hasattr(X, '_jdf'):
            retDF = DataFrame(output, self.sparkSession)
            # Return DF
            return retDF.sort('__INDEX')
        else:
            raise Exception('Unsupported input type')
        
    def predict_proba(self, X):
        """
        Invokes the transform_probability method on Estimator object on JVM if X and y are on of the supported data types
        Return predicted class probabilities for X.

        Parameters
        ----------
        X: NumPy ndarray, Pandas DataFrame, scipy sparse matrix or PySpark DataFrame
        """
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        if hasattr(X, '_jdf'):
            return self.predict(X)
        elif self.transferUsingDF:
            raise ValueError('The parameter transferUsingDF is not valid for the method predict_proba')
        try:
            if self.estimator is not None and self.model is not None:
                self.estimator.copyProperties(self.model)
        except AttributeError:
            pass
        try:
            if isinstance(X, str):
                return self.model.transform_probability(X)
            jX = self._convertPythonXToJavaObject(X)
            if default_jvm_stdout:
                with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                    return self._convertJavaOutputToPythonObject(X, self.model.transform_probability(jX))
            else:
                return self._convertJavaOutputToPythonObject(X, self.model.transform_probability(jX))
        except Py4JError:
            traceback.print_exc()
    
    # Returns either a DataFrame or MatrixBlock after calling transform(X:MatrixBlock, y:MatrixBlock) on Model object on JVM
    def predict(self, X):
        """
        Invokes the transform method on Estimator object on JVM if X and y are on of the supported data types

        Parameters
        ----------
        X: NumPy ndarray, Pandas DataFrame, scipy sparse matrix or PySpark DataFrame or file path
        """
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        try:
            if self.estimator is not None and self.model is not None:
                self.estimator.copyProperties(self.model)
        except AttributeError:
            pass
        try:
            if isinstance(X, str):
                return self.model.transform(X)
            jX = self._convertPythonXToJavaObject(X)
            if default_jvm_stdout:
                with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                    ret = self._convertJavaOutputToPythonObject(X, self.model.transform(jX))
            else:
                ret = self._convertJavaOutputToPythonObject(X, self.model.transform(jX))
            return self.decode(ret) if isinstance(X, SUPPORTED_TYPES) else ret
        except Py4JError:
            traceback.print_exc()

class BaseSystemMLClassifier(BaseSystemMLEstimator):

    def encode(self, y):
        self.le = LabelEncoder()
        self.le.fit(y)
        return self.le.transform(y) + 1
        
    def decode(self, y):
        if not hasattr(self, 'le'):
            self.le = None
        if not hasattr(self, 'labelMap'):
            self.labelMap = None
        if self.le is not None:
            return self.le.inverse_transform(np.asarray(y - 1, dtype=int))
        elif self.labelMap is not None:
            return [ self.labelMap[int(i)] for i in y ]
        else:
            return y
        
    def predict(self, X):
        predictions = super(BaseSystemMLClassifier, self).predict(X)
        from pyspark.sql.dataframe import DataFrame as df
        if type(predictions) == df:
            return predictions
        else:
            try:
                return np.asarray(predictions, dtype='double')
            except ValueError:
                print(type(predictions))
                return np.asarray(predictions, dtype='str')
            
    def score(self, X, y):
        """
        Scores the predicted value with ground truth 'y'

        Parameters
        ----------
        X: NumPy ndarray, Pandas DataFrame, scipy sparse matrix
        y: NumPy ndarray, Pandas DataFrame, scipy sparse matrix
        """
        predictions = np.asarray(self.predict(X))
        if np.issubdtype(predictions.dtype.type, np.number):
            return accuracy_score(y, predictions)
        else:
            return accuracy_score(np.asarray(y, dtype='str'), np.asarray(predictions, dtype='str'))
            
    def loadLabels(self, file_path):
        createJavaObject(self.sc, 'dummy')
        utilObj = self.sc._jvm.org.apache.sysml.api.ml.Utils()
        if utilObj.checkIfFileExists(file_path):
            df = self.sparkSession.read.csv(file_path, header=False).toPandas()
            keys = np.asarray(df._c0, dtype='int')
            values = np.asarray(df._c1, dtype='str')
            self.labelMap = {}
            for i in range(len(keys)):
                self.labelMap[int(keys[i])] = values[i]
            # self.encode(classes) # Giving incorrect results
        
    def load(self, weights, sep='/', eager=False):
        """
        Load a pretrained model. 

        Parameters
        ----------
        weights: directory whether learned weights are stored
        sep: seperator to use (default: '/')
        eager: load the model eagerly. This flag should be only used for debugging purposes. (default: False)
        """
        self.weights = weights
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        if default_jvm_stdout:
            with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                self.model.load(self.sc._jsc, weights, sep, eager)
        else:
            self.model.load(self.sc._jsc, weights, sep, eager)
        self.loadLabels(weights + '/labels.txt')
        
    def save(self, outputDir, format='binary', sep='/'):
        """
        Save a trained model.
        
        Parameters
        ----------
        outputDir: Directory to save the model to
        format: optional format (default: 'binary')
        sep: seperator to use (default: '/')
        """
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        if self.model != None:
            if default_jvm_stdout:
                with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                    self.model.save(self.sc._jsc, outputDir, format, sep)
            else:
                self.model.save(self.sc._jsc, outputDir, format, sep)

            labelMapping = None
            if hasattr(self, 'le') and self.le is not None:
                labelMapping = dict(enumerate(list(self.le.classes_), 1))
            elif hasattr(self, 'labelMap') and self.labelMap is not None:
                labelMapping = self.labelMap

            if labelMapping is not None:
                lStr = [ [ int(k), str(labelMapping[k]) ] for k in labelMapping ]
                df = self.sparkSession.createDataFrame(lStr)
                df.write.csv(outputDir + sep + 'labels.txt', mode='overwrite', header=False)
        else:
            raise Exception('Cannot save as you need to train the model first using fit')
        return self

class BaseSystemMLRegressor(BaseSystemMLEstimator):

    def encode(self, y):
        return y
        
    def decode(self, y):
        return y
    
    def score(self, X, y):
        """
        Scores the predicted value with ground truth 'y'

        Parameters
        ----------
        X: NumPy ndarray, Pandas DataFrame, scipy sparse matrix
        y: NumPy ndarray, Pandas DataFrame, scipy sparse matrix
        """
        return r2_score(y, self.predict(X), multioutput='variance_weighted')
        
    def load(self, weights=None, sep='/', eager=False):
        """
        Load a pretrained model. 

        Parameters
        ----------
        weights: directory whether learned weights are stored (default: None)
        sep: seperator to use (default: '/')
        eager: load the model eagerly (default: False)
        """
        self.weights = weights
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        if default_jvm_stdout:
            with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                self.model.load(self.sc._jsc, weights, sep, eager)
        else:
            self.model.load(self.sc._jsc, weights, sep, eager)

    def save(self, outputDir, format='binary', sep='/'):
        """
        Save a trained model.
        
        Parameters
        ----------
        outputDir: Directory to save the model to
        format: optional format (default: 'binary')
        sep: seperator to use (default: '/')
        """
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        if self.model != None:
            if default_jvm_stdout:
                with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                    self.model.save(outputDir, format, sep)
            else:
                self.model.save(outputDir, format, sep)
        else:
            raise Exception('Cannot save as you need to train the model first using fit')
        return self


class LogisticRegression(BaseSystemMLClassifier):
    """
    Performs both binomial and multinomial logistic regression.

    Examples
    --------
    
    Scikit-learn way
    
    >>> from sklearn import datasets, neighbors
    >>> from systemml.mllearn import LogisticRegression
    >>> from pyspark.sql import SparkSession
    >>> sparkSession = SparkSession.builder.getOrCreate()
    >>> digits = datasets.load_digits()
    >>> X_digits = digits.data
    >>> y_digits = digits.target + 1
    >>> n_samples = len(X_digits)
    >>> X_train = X_digits[:.9 * n_samples]
    >>> y_train = y_digits[:.9 * n_samples]
    >>> X_test = X_digits[.9 * n_samples:]
    >>> y_test = y_digits[.9 * n_samples:]
    >>> logistic = LogisticRegression(sparkSession)
    >>> print('LogisticRegression score: %f' % logistic.fit(X_train, y_train).score(X_test, y_test))
    
    MLPipeline way
    
    >>> from pyspark.ml import Pipeline
    >>> from systemml.mllearn import LogisticRegression
    >>> from pyspark.ml.feature import HashingTF, Tokenizer
    >>> from pyspark.sql import SparkSession
    >>> sparkSession = SparkSession.builder.getOrCreate()
    >>> training = sparkSession.createDataFrame([
    >>>     (0L, "a b c d e spark", 1.0),
    >>>     (1L, "b d", 2.0),
    >>>     (2L, "spark f g h", 1.0),
    >>>     (3L, "hadoop mapreduce", 2.0),
    >>>     (4L, "b spark who", 1.0),
    >>>     (5L, "g d a y", 2.0),
    >>>     (6L, "spark fly", 1.0),
    >>>     (7L, "was mapreduce", 2.0),
    >>>     (8L, "e spark program", 1.0),
    >>>     (9L, "a e c l", 2.0),
    >>>     (10L, "spark compile", 1.0),
    >>>     (11L, "hadoop software", 2.0)
    >>> ], ["id", "text", "label"])
    >>> tokenizer = Tokenizer(inputCol="text", outputCol="words")
    >>> hashingTF = HashingTF(inputCol="words", outputCol="features", numFeatures=20)
    >>> lr = LogisticRegression(sparkSession)
    >>> pipeline = Pipeline(stages=[tokenizer, hashingTF, lr])
    >>> model = pipeline.fit(training)
    >>> test = sparkSession.createDataFrame([
    >>>     (12L, "spark i j k"),
    >>>     (13L, "l m n"),
    >>>     (14L, "mapreduce spark"),
    >>>     (15L, "apache hadoop")], ["id", "text"])
    >>> prediction = model.transform(test)
    >>> prediction.show()
    
    """
    
    def __init__(self, sparkSession, penalty='l2', fit_intercept=True, normalize=False,  max_iter=100, max_inner_iter=0, tol=0.000001, C=1.0, solver='newton-cg', transferUsingDF=False):
        """
        Performs both binomial and multinomial logistic regression.
        
        Parameters
        ----------
        sparkSession: PySpark SparkSession
        penalty: Only 'l2' supported
        fit_intercept: Specifies whether to add intercept or not (default: True)
        normalize: This parameter is ignored when fit_intercept is set to False. (default: False)
        max_iter: Maximum number of outer (Fisher scoring) iterations (default: 100)
        max_inner_iter: Maximum number of inner (conjugate gradient) iterations, or 0 if no maximum limit provided (default: 0)
        tol: Tolerance used in the convergence criterion (default: 0.000001)
        C: 1/regularization parameter (default: 1.0 similar to scikit-learn. To disable regularization, please use float("inf"))
        solver: Only 'newton-cg' solver supported
        """
        self.sparkSession = sparkSession
        self.sc = sparkSession._sc
        createJavaObject(self.sc, 'dummy')
        self.uid = "logReg"
        self.estimator = self.sc._jvm.org.apache.sysml.api.ml.LogisticRegression(self.uid, self.sc._jsc.sc())
        self.estimator.setMaxOuterIter(max_iter)
        self.estimator.setMaxInnerIter(max_inner_iter)
        reg = 0.0 if C == float("inf") else 1.0 / C
        icpt = 2 if fit_intercept == True and normalize == True else int(fit_intercept)
        self.estimator.setRegParam(reg)
        self.estimator.setTol(tol)
        self.estimator.setIcpt(icpt)
        self.transferUsingDF = transferUsingDF
        self.setOutputRawPredictionsToFalse = True
        self.model = self.sc._jvm.org.apache.sysml.api.ml.LogisticRegressionModel(self.estimator)
        if penalty != 'l2':
            raise Exception('Only l2 penalty is supported')
        if solver != 'newton-cg':
            raise Exception('Only newton-cg solver supported')
        

class LinearRegression(BaseSystemMLRegressor):
    """
    Performs linear regression to model the relationship between one numerical response variable and one or more explanatory (feature) variables.
    
    Examples
    --------
    
    >>> import numpy as np
    >>> from sklearn import datasets
    >>> from systemml.mllearn import LinearRegression
    >>> from pyspark.sql import SparkSession
    >>> # Load the diabetes dataset
    >>> diabetes = datasets.load_diabetes()
    >>> # Use only one feature
    >>> diabetes_X = diabetes.data[:, np.newaxis, 2]
    >>> # Split the data into training/testing sets
    >>> diabetes_X_train = diabetes_X[:-20]
    >>> diabetes_X_test = diabetes_X[-20:]
    >>> # Split the targets into training/testing sets
    >>> diabetes_y_train = diabetes.target[:-20]
    >>> diabetes_y_test = diabetes.target[-20:]
    >>> # Create linear regression object
    >>> regr = LinearRegression(sparkSession, solver='newton-cg')
    >>> # Train the model using the training sets
    >>> regr.fit(diabetes_X_train, diabetes_y_train)
    >>> # The mean square error
    >>> print("Residual sum of squares: %.2f" % np.mean((regr.predict(diabetes_X_test) - diabetes_y_test) ** 2))
    
    """
    
    
    def __init__(self, sparkSession, fit_intercept=True, normalize=False, max_iter=100, tol=0.000001, C=float("inf"), solver='newton-cg', transferUsingDF=False):
        """
        Performs linear regression to model the relationship between one numerical response variable and one or more explanatory (feature) variables.

        Parameters
        ----------
        sparkSession: PySpark SparkSession
        fit_intercept: Specifies whether to add intercept or not (default: True)
        normalize: If True, the regressors X will be normalized before regression. This parameter is ignored when fit_intercept is set to False. (default: False)
        max_iter: Maximum number of conjugate gradient iterations, or 0 if no maximum limit provided (default: 100)
        tol: Tolerance used in the convergence criterion (default: 0.000001)
        C: 1/regularization parameter (default: float("inf") as scikit learn doesnot support regularization by default)
        solver: Supports either 'newton-cg' or 'direct-solve' (default: 'newton-cg').
        Depending on the size and the sparsity of the feature matrix, one or the other solver may be more efficient.
        'direct-solve' solver is more efficient when the number of features is relatively small (m < 1000) and
        input matrix X is either tall or fairly dense; otherwise 'newton-cg' solver is more efficient.
        """
        self.sparkSession = sparkSession
        self.sc = sparkSession._sc
        createJavaObject(self.sc, 'dummy')
        self.uid = "lr"
        if solver == 'newton-cg' or solver == 'direct-solve':
            self.estimator = self.sc._jvm.org.apache.sysml.api.ml.LinearRegression(self.uid, self.sc._jsc.sc(), solver)
        else:
            raise Exception('Only newton-cg solver supported')
        self.estimator.setMaxIter(max_iter)
        reg = 0.0 if C == float("inf") else 1.0 / C
        icpt = 2 if fit_intercept == True and normalize == True else int(fit_intercept)
        self.estimator.setRegParam(reg)
        self.estimator.setTol(tol)
        self.estimator.setIcpt(icpt)
        self.transferUsingDF = transferUsingDF
        self.setOutputRawPredictionsToFalse = False
        self.model = self.sc._jvm.org.apache.sysml.api.ml.LinearRegressionModel(self.estimator)


class SVM(BaseSystemMLClassifier):
    """
    Performs both binary-class and multiclass SVM (Support Vector Machines).

    Examples
    --------
    
    >>> from sklearn import datasets, neighbors
    >>> from systemml.mllearn import SVM
    >>> from pyspark.sql import SparkSession
    >>> sparkSession = SparkSession.builder.getOrCreate()
    >>> digits = datasets.load_digits()
    >>> X_digits = digits.data
    >>> y_digits = digits.target 
    >>> n_samples = len(X_digits)
    >>> X_train = X_digits[:.9 * n_samples]
    >>> y_train = y_digits[:.9 * n_samples]
    >>> X_test = X_digits[.9 * n_samples:]
    >>> y_test = y_digits[.9 * n_samples:]
    >>> svm = SVM(sparkSession, is_multi_class=True)
    >>> print('LogisticRegression score: %f' % svm.fit(X_train, y_train).score(X_test, y_test))
     
    """


    def __init__(self, sparkSession, fit_intercept=True, normalize=False, max_iter=100, tol=0.000001, C=1.0, is_multi_class=False, transferUsingDF=False):
        """
        Performs both binary-class and multiclass SVM (Support Vector Machines).

        Parameters
        ----------
        sparkSession: PySpark SparkSession
        fit_intercept: Specifies whether to add intercept or not (default: True)
        normalize: This parameter is ignored when fit_intercept is set to False. (default: False)
        max_iter: Maximum number iterations (default: 100)
        tol: Tolerance used in the convergence criterion (default: 0.000001)
        C: 1/regularization parameter (default: 1.0 similar to scikit-learn. To disable regularization, please use float("inf"))
        is_multi_class: Specifies whether to use binary-class SVM or multi-class SVM algorithm (default: False)
        """
        self.sparkSession = sparkSession
        self.sc = sparkSession._sc
        self.uid = "svm"
        createJavaObject(self.sc, 'dummy')
        self.is_multi_class = is_multi_class
        self.estimator = self.sc._jvm.org.apache.sysml.api.ml.SVM(self.uid, self.sc._jsc.sc(), is_multi_class)
        self.estimator.setMaxIter(max_iter)
        if C <= 0:
            raise Exception('C has to be positive')
        reg = 0.0 if C == float("inf") else 1.0 / C
        icpt = 2 if fit_intercept == True and normalize == True else int(fit_intercept)
        self.estimator.setRegParam(reg)
        self.estimator.setTol(tol)
        self.estimator.setIcpt(icpt)
        self.transferUsingDF = transferUsingDF
        self.setOutputRawPredictionsToFalse = False
        self.model = self.sc._jvm.org.apache.sysml.api.ml.SVMModel(self.estimator, self.is_multi_class)

class NaiveBayes(BaseSystemMLClassifier):
    """
    Performs Naive Bayes.

    Examples
    --------
    
    >>> from sklearn.datasets import fetch_20newsgroups
    >>> from sklearn.feature_extraction.text import TfidfVectorizer
    >>> from systemml.mllearn import NaiveBayes
    >>> from sklearn import metrics
    >>> from pyspark.sql import SparkSession
    >>> sparkSession = SparkSession.builder.getOrCreate(sc)
    >>> categories = ['alt.atheism', 'talk.religion.misc', 'comp.graphics', 'sci.space']
    >>> newsgroups_train = fetch_20newsgroups(subset='train', categories=categories)
    >>> newsgroups_test = fetch_20newsgroups(subset='test', categories=categories)
    >>> vectorizer = TfidfVectorizer()
    >>> # Both vectors and vectors_test are SciPy CSR matrix
    >>> vectors = vectorizer.fit_transform(newsgroups_train.data)
    >>> vectors_test = vectorizer.transform(newsgroups_test.data)
    >>> nb = NaiveBayes(sparkSession)
    >>> nb.fit(vectors, newsgroups_train.target)
    >>> pred = nb.predict(vectors_test)
    >>> metrics.f1_score(newsgroups_test.target, pred, average='weighted')

    """
    
    def __init__(self, sparkSession, laplace=1.0, transferUsingDF=False):
        """
        Performs Naive Bayes.

        Parameters
        ----------
        sparkSession: PySpark SparkSession
        laplace: Laplace smoothing specified by the user to avoid creation of 0 probabilities (default: 1.0)
        """
        self.sparkSession = sparkSession
        self.sc = sparkSession._sc
        self.uid = "nb"
        createJavaObject(self.sc, 'dummy')
        self.estimator = self.sc._jvm.org.apache.sysml.api.ml.NaiveBayes(self.uid, self.sc._jsc.sc())
        self.estimator.setLaplace(laplace)
        self.transferUsingDF = transferUsingDF
        self.setOutputRawPredictionsToFalse = False
        self.model = self.sc._jvm.org.apache.sysml.api.ml.NaiveBayesModel(self.estimator)

class Caffe2DML(BaseSystemMLClassifier):
    """
    Performs training/prediction for a given caffe network.
    
    Examples
    --------
    
    >>> from systemml.mllearn import Caffe2DML
    >>> from mlxtend.data import mnist_data
    >>> import numpy as np
    >>> from sklearn.utils import shuffle
    >>> X, y = mnist_data()
    >>> X, y = shuffle(X, y)
    >>> imgShape = (1, 28, 28)
    >>> import urllib
    >>> urllib.urlretrieve('https://raw.githubusercontent.com/niketanpansare/model_zoo/master/caffe/vision/lenet/mnist/lenet.proto', 'lenet.proto')
    >>> urllib.urlretrieve('https://raw.githubusercontent.com/niketanpansare/model_zoo/master/caffe/vision/lenet/mnist/lenet_solver.proto', 'lenet_solver.proto')
    >>> caffe2DML = Caffe2DML(spark, 'lenet_solver.proto').set(max_iter=500)
    >>> caffe2DML.fit(X, y)
    """
    def __init__(self, sparkSession, solver, input_shape, transferUsingDF=False):
        """
        Performs training/prediction for a given caffe network. 

        Parameters
        ----------
        sparkSession: PySpark SparkSession
        solver: caffe solver file path
        input_shape: 3-element list (number of channels, input height, input width)
        transferUsingDF: whether to pass the input dataset via PySpark DataFrame (default: False)
        """
        self.sparkSession = sparkSession
        self.sc = sparkSession._sc
        createJavaObject(self.sc, 'dummy')
        self.uid = "Caffe2DML"
        self.model = None
        if len(input_shape) != 3:
            raise ValueError('Expected input_shape as list of 3 element')
        solver = self.sc._jvm.org.apache.sysml.api.dl.Utils.readCaffeSolver(solver)
        self.estimator = self.sc._jvm.org.apache.sysml.api.dl.Caffe2DML(self.sc._jsc.sc(), solver, str(input_shape[0]), str(input_shape[1]), str(input_shape[2]))
        self.transferUsingDF = transferUsingDF
        self.setOutputRawPredictionsToFalse = False

    def load(self, weights=None, sep='/', ignore_weights=None, eager=False):
        """
        Load a pretrained model. 

        Parameters
        ----------
        weights: directory whether learned weights are stored (default: None)
        sep: seperator to use (default: '/')
        ignore_weights: names of layers to not read from the weights directory (list of string, default:None)
        eager: load the model eagerly (default: False)
        """
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        self.weights = weights
        self.estimator.setInput("$weights", str(weights))
        self.model = self.sc._jvm.org.apache.sysml.api.dl.Caffe2DMLModel(self.estimator)
        if default_jvm_stdout:
            with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                self.model.load(self.sc._jsc, weights, sep, eager)
        else:
            self.model.load(self.sc._jsc, weights, sep, eager)
        self.loadLabels(weights + '/labels.txt')
        if ignore_weights is not None:
            self.estimator.setWeightsToIgnore(ignore_weights)
            
    def set(self, debug=None, train_algo=None, test_algo=None, parallel_batches=None, output_activations=None, perform_one_hot_encoding=None, parfor_parameters=None):
        """
        Set input to Caffe2DML
        
        Parameters
        ----------
        debug: to add debugging DML code such as classification report, print DML script, etc (default: False)
        train_algo: can be minibatch, batch, allreduce_parallel_batches or allreduce (default: minibatch)
        test_algo: can be minibatch, batch, allreduce_parallel_batches or allreduce (default: minibatch)
        parallel_batches: number of parallel batches
        output_activations: (developer flag) directory to output activations of each layer as csv while prediction. To be used only in batch mode (default: None)
        perform_one_hot_encoding: should perform one-hot encoding in DML using table function (default: False)
        parfor_parameters: dictionary for parfor parameters when using allreduce-style algorithms (default: "")
        """
        if debug is not None: self.estimator.setInput("$debug", str(debug).upper())
        if train_algo is not None: self.estimator.setInput("$train_algo", str(train_algo).lower())
        if test_algo is not None: self.estimator.setInput("$test_algo", str(test_algo).lower())
        if parallel_batches is not None: self.estimator.setInput("$parallel_batches", str(parallel_batches))
        if output_activations is not None: self.estimator.setInput("$output_activations", str(output_activations))
        if perform_one_hot_encoding is not None: self.estimator.setInput("$perform_one_hot_encoding", str(perform_one_hot_encoding).lower())
        if parfor_parameters is not None:
            if isinstance(parfor_parameters, dict):
                # Convert dictionary to comma-separated list
                parfor_parameters = ''.join([ ', ' + str(k) + '=' + str(v) for k, v in parfor_parameters.items()]) if len(parfor_parameters) > 0 else ''
                self.estimator.setInput("$parfor_parameters", parfor_parameters)
            else:
                raise TypeError("parfor_parameters should be a dictionary") 
        return self
    
    def summary(self):
        """
        Print the summary of the network
        """
        import pyspark
        global default_jvm_stdout, default_jvm_stdout_parallel_flush
        if type(self.sparkSession) == pyspark.sql.session.SparkSession:
            if default_jvm_stdout:
                with jvm_stdout(parallel_flush=default_jvm_stdout_parallel_flush):
                    self.estimator.summary(self.sparkSession._jsparkSession)
            else:
                self.estimator.summary(self.sparkSession._jsparkSession)
        else:
            raise TypeError('Please use spark session of type pyspark.sql.session.SparkSession in the constructor')
    
    
class Keras2DML(Caffe2DML):
    """
    Peforms training/prediction for a given keras model.


    """

    def __init__(self, sparkSession, keras_model, input_shape, transferUsingDF=False, load_keras_weights=True, weights=None, labels=None, batch_size=64, max_iter=2000, test_iter=10, test_interval=500, display=100, lr_policy="step", weight_decay=5e-4, regularization_type="L2"):
        """
        Performs training/prediction for a given keras model.

        Parameters
        ----------
        sparkSession: PySpark SparkSession
        keras_model: keras model
        input_shape: 3-element list (number of channels, input height, input width)
        transferUsingDF: whether to pass the input dataset via PySpark DataFrame (default: False)
        load_keras_weights: whether to load weights from the keras_model. If False, the weights will be initialized to random value using NN libraries' init method  (default: True)
        weights: directory whether learned weights are stored (default: None)
        labels: file containing mapping between index and string labels (default: None)
        batch_size: size of the input batch (default: 64)
        max_iter: maximum number of iterations (default: 1)
        test_iter: test_iter for caffe solver (default: 10)
        test_interval: test_interval for caffe solver (default: 500)
        display: display for caffe solver (default: 100)
        lr_policy: learning rate policy for caffe solver (default: "step")
        weight_decay: regularation strength (default: 5e-4)
        regularization_type: regularization type (default: "L2")
        """
        from .keras2caffe import convertKerasToCaffeNetwork, convertKerasToCaffeSolver, convertKerasToSystemMLModel, getNumPyMatrixFromKerasWeight, lossLayerStr, getInputMatrices

        import tempfile
        if type(keras_model) == keras.models.Sequential:
            # Convert the sequential model to functional model
            if keras_model.model is None:
                keras_model.build()
            keras_model = keras_model.model
        self.name = keras_model.name
        createJavaObject(sparkSession._sc, 'dummy')
        if not hasattr(keras_model, 'optimizer'):
            keras_model.compile(loss='categorical_crossentropy', optimizer=keras.optimizers.SGD(lr=0.01, momentum=0.95, decay=5e-4, nesterov=True))
        convertKerasToCaffeNetwork(keras_model, self.name + ".proto", int(batch_size))
        convertKerasToCaffeSolver(keras_model, self.name + ".proto", self.name + "_solver.proto", int(max_iter), int(test_iter), int(test_interval), int(display), lr_policy, weight_decay, regularization_type)
        self.weights = tempfile.mkdtemp() if weights is None else weights
        if load_keras_weights:
            convertKerasToSystemMLModel(sparkSession, keras_model, self.weights)
        if labels is not None and (labels.startswith('https:') or labels.startswith('http:')):
            import urllib
            urllib.urlretrieve(labels, os.path.join(weights, 'labels.txt'))
        elif labels is not None:
            from shutil import copyfile
            copyfile(labels, os.path.join(weights, 'labels.txt'))
        super(Keras2DML,self).__init__(sparkSession, self.name + "_solver.proto", input_shape, transferUsingDF)
        if load_keras_weights:
            self.load(self.weights)

    def close(self):
        import shutil
        shutil.rmtree(weights)
