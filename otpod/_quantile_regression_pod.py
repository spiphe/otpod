# -*- coding: utf-8 -*-
# -*- Python -*-

__all__ = ['QuantileRegressionPOD']

import openturns as ot
import numpy as np
from ._pod import POD
# from _quantile_regression import QuantReg
from statsmodels.regression.quantile_regression import QuantReg
from statsmodels.regression.linear_model import OLS
from scipy.interpolate import interp1d
from _decorator import DocInherit, keepingArgs
import matplotlib.pyplot as plt


class QuantileRegressionPOD(POD):
    """
    Quantile regression based POD.

    **Available constructors:**

    QuantileRegressionPOD(*inputSample, outputSample, detection, noiseThres,
    saturationThres, boxCox, quantile*)

    Parameters
    ----------
    inputSample : 2-d sequence of float
        Vector of the defect sizes, of dimension 1.
    outputSample : 2-d sequence of float
        Vector of the signals, of dimension 1.
    detection : float
        Detection value of the signal.
    noiseThres : float
        Value for low censored data. Default is None.
    saturationThres : float
        Value for high censored data. Default is None
    boxCox : bool or float
        Enable or not the Box Cox transformation. If boxCox is a float, the Box
        Cox transformation is enabled with the given value. Default is False.
    quantile : list of float
        List of quantile value to perform the regression. Default is a list
        from 0.05 to 0.95 with a step of 0.05.

    Notes
    -----
    This class aims at building the POD based on a quantile regression
    model. The POD model corresponds with interpolate function built whose POD
    values are computed using the quantile values given as parameters.

    However, the computeDetectionSize method calls the real quantile regression
    at the given probability level.
    """

    def __init__(self, inputSample=None, outputSample=None, detection=None, noiseThres=None,
                 saturationThres=None, boxCox=False, quantile=np.linspace(0.05, 0.98, 21)):

        self._quantile = np.hstack(quantile)

        # if self._resDistFact is not None:
        #     if self._resDistFact.getClassName() == 'NormalFactory':
        #         raise Exception('Not yet implemented.')

        # initialize the POD class
        super(QuantileRegressionPOD, self).__init__(inputSample, outputSample,
                                 detection, noiseThres, saturationThres, boxCox)
        # inherited attributes
        self._simulationSize = 100
        # self._detection
        # self._inputSample
        # self._outputSample
        # self._noiseThres
        # self._saturationThres        
        # self._lambdaBoxCox
        # self._boxCox
        # self._size
        # self._dim
        # self._censored
        
        # assertion input dimension is 1
        assert (self._dim == 1), "InputSample must be of dimension 1."


    def run(self):
        
        # Run the preliminary run of the POD class
        result = self._run(self._inputSample, self._outputSample, self._detection,
                           self._noiseThres, self._saturationThres, self._boxCox,
                           self._censored)

        # get some results
        self._defects = result['defects']
        self._signals = result['signals']
        self._detectionBoxCox = result['detectionBoxCox']

        defectsSize = self._defects.getSize()

        X = ot.NumericalSample(defectsSize, [1, 0])
        X[:, 1] = self._defects
        self._algoQuantReg = QuantReg(np.array(self._signals), np.array(X))
        # self._initialBeta = OLS(np.array(self._signals), np.array(X)).fit().params

        defectMax = self._defects.getMax()[0]
        defectList = []
        for probLevel in self._quantile:
            model = self._buildModel(1. - probLevel)
            # Solve the model == detectionBoxCox with defects 
            # boundaries = [0, defectMax]
            defectList.append(ot.Brent().solve(model, self._detectionBoxCox,
                                               0, defectMax))
        # create support of the interpolating function including zero
        # add point (0, 0) and point (defectMax, max(quantile))
        xvalue = np.hstack([0, defectList, defectMax])
        yvalue = np.hstack([0., self._quantile, self._quantile.max()])
        interpModel = interp1d(xvalue, yvalue, kind='linear')
        self._PODmodel = ot.PythonFunction(1, 1, interpModel)


        ############ Confidence interval with bootstrap ########################
        # Compute a NsimulationSize defect sizes for all quantiles
        data = ot.NumericalSample(self._size, 2)
        data[:, 0] = self._inputSample
        data[:, 1] = self._outputSample
        # bootstrap of the data
        bootstrapExp = ot.BootstrapExperiment(data)
        self._defectsPerQuantile = ot.NumericalSample(self._simulationSize, self._quantile.size)
        for i in range(self._simulationSize):
            # generate a sample with replacement within data of the same size
            bootstrapData = bootstrapExp.generate()
            result = self._run(bootstrapData[:,0], bootstrapData[:,1], self._detection,
                               self._noiseThres, self._saturationThres,
                               self._boxCox, self._censored)

            # get some results
            defects = result['defects']
            signals = result['signals']
            detectionBoxCox = result['detectionBoxCox']
            defectsSize = defects.getSize()

            # new quantile regression algorithm
            X = ot.NumericalSample(defectsSize, [1, 0])
            X[:, 1] = defects
            algoQuantReg = QuantReg(np.array(signals), np.array(X))

            # compute the quantile defects
            defectMax = defects.getMax()[0]
            defectList = []
            for probLevel in self._quantile:
                fit = algoQuantReg.fit(1. - probLevel, max_iter=300, p_tol=1e-2)
                def model(x):
                    X = ot.NumericalPoint([1, x[0]])
                    return ot.NumericalPoint(fit.predict(X))
                model = ot.PythonFunction(1, 1, model)
                # Solve the model == detectionBoxCox with defects 
                # boundaries = [0, defectMax]
                defectList.append(ot.Brent().solve(model, detectionBoxCox,
                                                   0, defectMax))
            # add the quantile in the numerical sample as the ith simulation
            self._defectsPerQuantile[i, :] = defectList

    def getPODModel(self):
        """
        Accessor to the POD model.

        Returns
        -------
        PODModel : :py:class:`openturns.NumericalMathFunction`
            The function which computes the probability of detection for a given
            defect value.
        """
        return self._PODmodel

    def getPODCLModel(self, confidenceLevel=0.95):
        """
        Accessor to the POD model at a given confidence level.

        confidenceLevel : float
            The confidence level the POD must be computed. Default is 0.95

        Returns
        -------
        PODModelCl : :py:class:`openturns.NumericalMathFunction`
            The function which computes the probability of detection for a given
            defect value at the confidence level given as parameter.
        """
        defectsQuantile = self._defectsPerQuantile.computeQuantilePerComponent(
                                                                confidenceLevel)

        xvalue = np.hstack([0, np.array(defectsQuantile), self._defects.getMax()[0]])
        yvalue = np.hstack([0., self._quantile, self._quantile.max()])
        interpModel = interp1d(xvalue, yvalue, kind='linear')
        PODmodelCl = ot.PythonFunction(1, 1, interpModel)

        return PODmodelCl

    @DocInherit # decorator to inherit the docstring from POD class
    @keepingArgs # decorator to keep the real signature
    def computeDetectionSize(self, probabilityLevel, confidenceLevel=None):
        defectMin = self._inputSample.getMin()[0]
        defectMax = self._inputSample.getMax()[0]
        # compute 'a90'
        model = self._buildModel(1. - probabilityLevel)
        detectionSize = ot.NumericalPointWithDescription(1, ot.Brent().solve(
                                    model, self._detectionBoxCox, 0, defectMax))
        description = ['a'+str(int(probabilityLevel*100))]

        # compute 'a90_95'
        if confidenceLevel is not None:
            detectionSize.add(ot.Brent().solve(self.getPODCLModel(confidenceLevel),
                                               probabilityLevel,
                                               defectMin, defectMax))
            description.append('a'+str(int(probabilityLevel*100))+'/'\
                                                +str(int(confidenceLevel*100)))
        # add description to the NumericalPoint
        detectionSize.setDescription(description)
        return detectionSize

    @DocInherit # decorator to inherit the docstring from POD class
    @keepingArgs # decorator to keep the real signature
    def drawPOD(self, probabilityLevel=None, confidenceLevel=None, defectMin=None,
                defectMax=None, nbPt=100, name=None):

        if confidenceLevel is None:
            fig, ax = self._drawPOD(self.getPODModel(), None,
                                probabilityLevel, confidenceLevel, defectMin,
                                defectMax, nbPt, name)
        elif confidenceLevel is not None:
            fig, ax = self._drawPOD(self.getPODModel(), self.getPODCLModel(confidenceLevel),
                    probabilityLevel, confidenceLevel, defectMin,
                    defectMax, nbPt, name)

        ax.set_title('POD - Quantile regression model')
        if name is not None:
            fig.savefig(name, bbox_inches='tight', transparent=True)

        return fig, ax


    def _buildModel(self, probabilityLevel):
        """
        Build the NumericalMathFunction at the given probabilityLevel. It is
        used in the run and in computeDetectionSize in order to do not use the
        interpolate function.
        """
        fit = self._algoQuantReg.fit(probabilityLevel, max_iter=300, p_tol=1e-2)
        def model(x):
            X = ot.NumericalPoint([1, x[0]])
            return ot.NumericalPoint(fit.predict(X))
        return ot.PythonFunction(1, 1, model)


    def drawLinearModel(self, probabilityLevel, name=None):
        """
        Draw the linear regression prediction versus the true data.

        Parameters
        ----------
        probabilityLevel : float
            The probability level for which the quantile regression is performed
        name : string
            name of the figure to be saved with *transparent* option sets to True
            and *bbox_inches='tight'*. It can be only the file name or the 
            full path name. Default is None.

        Returns
        -------
        fig : `matplotlib.figure <http://matplotlib.org/api/figure_api.html>`_
            Matplotlib figure object.
        ax : `matplotlib.axes <http://matplotlib.org/api/axes_api.html>`_
            Matplotlib axes object.
        """

        model = self._algoQuantReg.fit(1. - probabilityLevel)

        defects = self._defects
        signals = self._signals
        fittedSignals = model.fittedvalues

        fig, ax = plt.subplots(figsize=(8, 6))
        ax.plot(defects, signals, 'b.', label='Data', ms=9)
        ax.plot(defects, fittedSignals, 'r-', label='Linear regression model')
        ax.set_xlabel('Defects')
        ax.set_ylabel('Signals')
        ax.set_title('Quantile regression model at level (1 - ' + \
                                        str(probabilityLevel) + ')')
        ax.grid()
        ax.legend(loc='upper left')

        if name is not None:
            fig.savefig(name, bbox_inches='tight', transparent=True)

        return fig, ax