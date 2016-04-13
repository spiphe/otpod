# -*- coding: utf-8 -*-
# -*- Python -*-

__all__ = ['UnivariateLinearModelPOD']

import openturns as ot
import math as m
from ._pod import POD
from . import UnivariateLinearModelAnalysis as LinearAnalysis
from ._math_tools import computeBoxCox, censureFilter, computeLinearParametersCensored
from statsmodels.regression.linear_model import OLS
import numpy as np


class _Results():
    """
    This class contains the result of the run. Instances are created
    for uncensored data or if needed for censored data.
    """
    def __init__(self):
        pass

class UnivariateLinearModelPOD(POD):

    """
    Linear regression based POD.

    **Available constructors:**

    UnivariateLinearModelPOD(*analysis=analysis, detection=detection*)

    UnivariateLinearModelPOD(*inputSample, outputSample, detection, noiseThres,
    saturationThres, resDistFact, boxCox*)

    Parameters
    ----------
    analysis : :class:`UnivariateLinearModelAnalysis`
        Linear analysis object.
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
    resDistFact : :py:class:`openturns.DistributionFactory`
        Distribution hypothesis followed by the residuals. Default is None.
    boxCox : bool or float
        Enable or not the Box Cox transformation. If boxCox is a float, the Box
        Cox transformation is enabled with the given value. Default is False.

    Notes
    -----
    This class aims at building the POD based on a linear regression
    model. If a linear analysis has been launched, it can be used as prescribed 
    in the first constructor. Otherwise, parameters must be given as in the
    second constructor.

    Following the given distribution in *resDistFact*, the POD model is built
    different hypothesis:

    - if *resDistFact = None*, it corresponds with Berens-Binomial. This
      is the default case. 
    - if *resDistFact* = :py:class:`openturns.NormalFactory`, it corresponds with Berens-Gauss.
    - if *resDistFact* = {:py:class:`openturns.KernelSmoothing`,
      :py:class:`openturns.WeibullFactory`, ...}, the confidence interval is
      built by bootstrap.

    """

    def __init__(self, inputSample=None, outputSample=None, detection=None, noiseThres=None,
                 saturationThres=None, resDistFact=None, boxCox=False,
                 analysis=None):

        #  Constructor with analysis given, check if analysis is only given with detection.
        self._analysis = analysis
        if self._analysis is not None:
            try:
                assert (inputSample is None)
                assert (outputSample is None)
                assert (noiseThres is None)
                assert (saturationThres is None)
                assert (resDistFact is None)
                assert (detection is not None)
            except:
                raise AttributeError('The constructor available with a linear '+\
                                     'analysis as parameter must only have ' + \
                                     'the detection parameter.')

        ############# Run the linear analysis if not given #####################
        if self._analysis is not None:
        #     # compute the 
        #     self._analysis = LinearAnalysis(inputSample, outputSample, noiseThres,
        #                                     saturationThres, resDistFact, boxCox)
        #     boxCox = self._analysis.getBoxCoxParameter()
        # else:
            # get back informations from analysis on input parameters
            inputSample = self._analysis.getInputSample()
            outputSample = self._analysis.getOutputSample()
            noiseThres = self._analysis.getNoiseThreshold()
            saturationThres = self._analysis.getSaturationThreshold()
            # check if box cox was enabled or not.
            boxCox = self._analysis.getBoxCoxParameter()

        # initialize the POD class
        super(UnivariateLinearModelPOD, self).__init__(inputSample, outputSample,
                                 detection, noiseThres, saturationThres, boxCox)
        # inherited attributes
        # self._simulationSize
        # self._detection
        # self._inputSample
        # self._outputSample
        # self._noiseThres
        # self._saturationThres        
        # self._lambdaBoxCox
        # self._boxCox
        # self._size
        # self._dim

        # residuals distribution factory attributes
        self._resDistFact = resDistFact

        #################### check attributes for censoring ####################
        # Add flag to tell if censored data must taken into account or not.
        if self._noiseThres is not None or self._saturationThres is not None:
            # flag to tell censoring is enabled
            self._censored = True
            # Results instances are created for both cases.
            self._resultsCens = _Results()
            self._resultsUnc = _Results()
        else:
            self._censored = False
            # Results instance is created only for uncensored case.
            self._resultsUnc = _Results()
        
        # assertion input dimension is 1
        assert (self._dim == 1), "InputSample must be of dimension 1."


    def run(self):
        """
        Bla bla bla
        """


        results = _computeLinearModel(self._inputSample, self._outputSample,
                                      self._detection, self._noiseThres,
                                      self._saturationThres, self._boxCox,
                                      self._censored)
        # contains intercept, slope, stderr, residuals
        self._resultsUnc = results['uncensored']
        self._resultsCens = results['censored']
        # return the box cox detection even if box cox was not enabled. In this
        # case detection = detectionBoxCox
        self._detectionBoxCox = results['detection']

        ############# get results from analsys and build linear model ##########
        # define the linear model
        def LinModel(x):
            return self._resultsUnc.intercept + self._resultsUnc.slope * x
        self._resultsUnc.linearModel = LinModel

        if self._censored:
             # define the linear model
            def LinModelCensored(x):
                return self._resultsCens.intercept + self._resultsCens.slope * x
            self._resultsCens.linearModel = LinModelCensored

        ######################## build PODModel function #######################
        if self._resDistFact is None:
            # Berens Binomial
            PODfunction = self._PODbinomialModel(self._resultsUnc.residuals,
                                                 self._resultsUnc.linearModel)
        else:
            # Linear regression model + bootstrap
            PODfunction = self._PODbootstrapModel(self._resultsUnc.residuals,
                                                  self._resultsUnc.linearModel)

        self._resultsUnc.PODmodel = ot.PythonFunction(1, 1, PODfunction)

        # Create POD model for the censored case
        if self._censored:
            if self._resDistFact is None:
                # Berens Binomial
                PODfunction = self._PODbinomialModel(self._resultsCens.residuals,
                                                     self._resultsCens.linearModel)
            else:
                # Linear regression model + bootstrap
                PODfunction = self._PODbootstrapModel(self._resultsCens.residuals,
                                                      self._resultsCens.linearModel)

            self._resultsCens.PODmodel = ot.PythonFunction(1, 1, PODfunction)


        ############## build PODModel function with conf interval ##############
        # Berens binomial : build directly in the get method

        # Linear regression model + bootstrap : build the collection of function
        # which is time consuming. The final PODmodelCl is built in the get method 
        if self._resDistFact is not None and \
           self._resDistFact.getClassName() is not 'NormalFactory':
            self._PODcollDict = self._PODbootstrapModelCl()



    def getPODModel(self, model='uncensored'):
        """
        Accessor to the POD model.

        Parameters
        ----------
        model : string
            The linear regression model to be used, either *uncensored* or
            *censored* if censored threshold were given. Default is *uncensored*.

        Returns
        -------
        PODModel : :py:class:`openturns.NumericalMathFunction`
            The function which computes the probability of detection for a given
            defect value.
        """

        # Check is the censored model exists when asking for it 
        if model == "censored" and not self._censored:
            raise NameError('POD model for censored data is not available.')

        if model == "uncensored":
            PODmodel = self._resultsUnc.PODmodel
        elif model == "censored":
            PODmodel = self._resultsCen.PODmodel
        else:
            raise NameError("model can be 'uncensored' or 'censored'.")

        return PODmodel

    def getPODCLModel(self, model='uncensored', confLevel=0.95):
        """
        Accessor to the POD model at a given confidence level.

        Parameters
        ----------
        model : string
            The linear regression model to be used, either *uncensored* or
            *censored* if censored threshold were given. Default is *uncensored*.
        confLevel : float
            The confidence level the POD must be computed. Default is 0.95

        Returns
        -------
        PODModelCl : :py:class:`openturns.NumericalMathFunction`
            The function which computes the probability of detection for a given
            defect value at the confidence level given as parameter.
        """

        # Check is the censored model exists when asking for it 
        if model == "censored" and not self._censored:
            raise NameError('Linear model for censored data is not available.')

        if model == "uncensored":
            if self._resDistFact is None:
                # Berens Binomial
                PODfunction = self._PODbinomialModelCl(self._resultsUnc.residuals,
                                                       self._resultsUnc.linearModel,
                                                       confLevel)
            else:
                # Linear regression model + bootstrap
                def PODfunction(x):
                    samplePODDef = ot.NumericalSample(self._simulationSize, 1)
                    for i in range(self._simulationSize):
                        samplePODDef[i] = [self._PODcollDict['Uncensored'][i](x[0])]
                    return samplePODDef.computeQuantilePerComponent(1. - confLevel)

            PODmodelCl = ot.PythonFunction(1, 1, PODfunction)

        elif model == "censored":
        # Create model conf interval for the censored case
            if self._resDistFact is None:
                # Berens Binomial
                PODfunction = self._PODbinomialModelCl(self._resultsCens.residuals,
                                                       self._resultsCens.linearModel,
                                                       confLevel)
            else:
                # Linear regression model + bootstrap
                def PODfunction(x):
                    samplePODDef = ot.NumericalSample(self._simulationSize, 1)
                    for i in range(self._simulationSize):
                        samplePODDef[i] = [self._PODcollDict['Censored'][i](x[0])]
                    return samplePODDef.computeQuantilePerComponent(1. - confLevel)

            PODmodelCl = ot.PythonFunction(1, 1, PODfunction)
        else:
            raise NameError("model can be 'uncensored' or 'censored'.")

        return PODmodelCl

################################################################################
####################### Linear regression Binomial #############################
################################################################################

    def _PODbinomialModel(self, residuals, linearModel):
        empiricalDist = ot.UserDefined(residuals)
        # function to compute the POD(defect)
        def PODmodel(x):
            def_threshold = self._detectionBoxCox - linearModel(x[0])
            # Nb of residuals > threshold(defect) / N
            return [empiricalDist.computeComplementaryCDF(def_threshold)]
        return PODmodel

    def _PODbinomialModelCl(self, residuals, linearModel, confLevel):
        empiricalDist = ot.UserDefined(residuals)
        sizeResiduals = residuals.getSize()
        def PODmodelCl(x):
            # Nb of residuals > threshold - linModel(defect)
            def_threshold = self._detectionBoxCox - linearModel(x[0])
            NbDepDef = m.trunc(sizeResiduals * empiricalDist.computeComplementaryCDF(def_threshold))
            # Particular case : NbDepDef == sizeResiduals
            if NbDepDef == sizeResiduals:
                pod = confLevel**(1. / sizeResiduals)
            else:
                # 1 - quantile(confLevel) of distribution Beta(r, s)
                pod = 1-ot.DistFunc.qBeta(sizeResiduals - NbDepDef, NbDepDef + 1, confLevel)
            return [pod]
        return PODmodelCl


################################################################################
####################### Linear regression bootstrap ############################
################################################################################


    def _PODbootstrapModel(self, residuals, linearModel):
        empiricalDist = self._resDistFact.build(residuals)
        # function to compute the POD(defects)
        def PODmodel(x):
            def_threshold = self._detectionBoxCox - linearModel(x[0])
            # Nb of residuals > threshold(defect) / N
            return [empiricalDist.computeComplementaryCDF(def_threshold)]
        return PODmodel

    def _PODbootstrapModelCl(self):

        class buildPODModel():
            def __init__(self, inputSample, outputSample, detection, noiseThres,
                            saturationThres, resDistFact, boxCox, censored):

                results = _computeLinearModel(inputSample, outputSample, detection,
                                        noiseThres, saturationThres, boxCox, censored)

                self.detection = results['detection']
                self.resultsUnc = results['uncensored']
                self.resultsCens = results['censored']
                self.resultsUnc.resDist = resDistFact.build(self.resultsUnc.residuals)
                if censored:
                    self.resultsCens.resDist = resDistFact.build(self.resultsCens.residuals)

            def PODmodel(self, x):
                defectThres = self.detection - (self.resultsUnc.intercept + 
                              self.resultsUnc.slope * x)
                return self.resultsUnc.resDist.computeComplementaryCDF(defectThres)

            def PODmodelCens(self, x):
                defectThres = self.detection - (self.resultsCens.intercept +
                              self.resultsCens.slope * x)
                return self.resultsCens.resDist.computeComplementaryCDF(defectThres)

        data = ot.NumericalSample(self._size, 2)
        data[:, 0] = self._inputSample
        data[:, 1] = self._outputSample
        # bootstrap of the data
        bootstrapExp = ot.BootstrapExperiment(data)
        PODcollUnc = []
        PODcollCens = []
        for i in range(self._simulationSize):
        # generate a sample with replacement within data of the same size
            bootstrapData = bootstrapExp.generate()
            # compute the linear models
            model = buildPODModel(bootstrapData[:,0], bootstrapData[:,1],
                                  self._detection, self._noiseThres,
                                  self._saturationThres, self._resDistFact,
                                  self._boxCox, self._censored)

            PODcollUnc.append(model.PODmodel)

            # computing in the censored case
            if self._censored:
                PODcollCens.append(model.PODmodelCens)

        return {'Uncensored':PODcollUnc, 'Censored':PODcollCens}


################################################################################
####################### Compute linear regression  #############################
################################################################################

def _computeLinearModel(inputSample, outputSample, detection, noiseThres,
                        saturationThres, boxCox, censored):
    """
    run the same code as in the linear analysis class but without the test
    this is much faster doing it.
    It is also needed for the POD bootstrap method.
    """

    ## create result container
    resultsUnc = _Results()
    resultsCens = _Results()
    #################### Filter censored data ##############################
    if censored:
        # check if one sided censoring
        if noiseThres is None:
            noiseThres = -ot.sys.float_info.max
        if saturationThres is None:
            saturationThres = ot.sys.float_info.max
        # Filter censored data
        defects, defectsNoise, defectsSat, signals = \
            censureFilter(inputSample, outputSample,
                          noiseThres, saturationThres)
    else:
        defects, signals = inputSample, outputSample

    defectsSize = defects.getSize()

    ###################### Box Cox transformation ##########################
    # Compute Box Cox if enabled
    if boxCox:
        # optimization required, get optimal lambda and graph
        lambdaBoxCox, graphBoxCox = computeBoxCox(defects, signals)

        # Transformation of data
        boxCoxTransform = ot.BoxCoxTransform([lambdaBoxCox])
        signals = boxCoxTransform(signals)
        if censored:
            if noiseThres != -ot.sys.float_info.max:
                noiseThres = boxCoxTransform([noiseThres])[0]
            if saturationThres != ot.sys.float_info.max:
                saturationThres = boxCoxTransform([saturationThres])[0]
        detectionBoxCox = boxCoxTransform([detection])[0]
    else:
        noiseThres = noiseThres
        saturationThres = saturationThres
        detectionBoxCox = detection

    ######################### Linear Regression model ######################
    # Linear regression with statsmodels module
    # Create the X matrix : [1, inputSample]
    X = ot.NumericalSample(defectsSize, [1, 0])
    X[:, 1] = defects
    algoLinear = OLS(np.array(signals), np.array(X)).fit()

    resultsUnc.intercept = algoLinear.params[0]
    resultsUnc.slope = algoLinear.params[1]
    # get standard error estimates (residuals standard deviation)
    resultsUnc.stderr = np.sqrt(algoLinear.scale)
    # get residuals from algoLinear
    resultsUnc.residuals = ot.NumericalSample(np.vstack(algoLinear.resid))

    if censored:
        # define initial starting point for MLE optimization
        initialStartMLE = [resultsUnc.intercept, resultsUnc.slope,
                           resultsUnc.stderr]
        # MLE optimization
        res = computeLinearParametersCensored(initialStartMLE, defects,
            defectsNoise, defectsSat, signals, noiseThres, saturationThres)
        resultsCens.intercept = res[0]
        resultsCens.slope = res[1]
        resultsCens.stderr = res[2]
        resultsCens.residuals = signals - (resultsCens.intercept + resultsCens.slope * defects)

    return {'uncensored':resultsUnc, 'censored':resultsCens, 'detection':detectionBoxCox}