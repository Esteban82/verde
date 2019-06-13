"""
Functions for automating model selection through cross-validation.

Supports using a dask.distributed.Client object for parallelism. The
DummyClient is used as a serial version of the parallel client.
"""
import numpy as np
from sklearn.model_selection import KFold, ShuffleSplit

from .base import check_fit_input
from .utils import DummyClient


def train_test_split(coordinates, data, weights=None, **kwargs):
    r"""
    Split a dataset into a training and a testing set for cross-validation.

    Similar to :func:`sklearn.model_selection.train_test_split` but is tuned to
    work on multi-component spatial data with optional weights.

    Extra keyword arguments will be passed to
    :class:`sklearn.model_selection.ShuffleSplit`, except for ``n_splits``
    which is always 1.

    Parameters
    ----------
    coordinates : tuple of arrays
        Arrays with the coordinates of each data point. Should be in the
        following order: (easting, northing, vertical, ...).
    data : array or tuple of arrays
        the data values of each data point. If the data has more than one
        component, *data* must be a tuple of arrays (one for each component).
    weights : none or array or tuple of arrays
        if not none, then the weights assigned to each data point. If more than
        one data component is provided, you must provide a weights array for
        each data component (if not none).

    Returns
    -------
    train, test : tuples
        Each is a tuple = (coordinates, data, weights) generated by separating
        the input values randomly.

    Examples
    --------

    >>> import numpy as np
    >>> # Split 2-component data with weights
    >>> data = (np.array([1, 3, 5, 7]), np.array([0, 2, 4, 6]))
    >>> coordinates = (np.arange(4), np.arange(-4, 0))
    >>> weights = (np.array([1, 1, 2, 1]), np.array([1, 2, 1, 1]))
    >>> train, test = train_test_split(coordinates, data, weights,
    ...                                random_state=0)
    >>> print("Coordinates:", train[0], test[0], sep='\n  ')
    Coordinates:
      (array([3, 1, 0]), array([-1, -3, -4]))
      (array([2]), array([-2]))
    >>> print("Data:", train[1], test[1], sep='\n  ')
    Data:
      (array([7, 3, 1]), array([6, 2, 0]))
      (array([5]), array([4]))
    >>> print("Weights:", train[2], test[2], sep='\n  ')
    Weights:
      (array([1, 1, 1]), array([1, 2, 1]))
      (array([2]), array([1]))
    >>> # Split single component data without weights
    >>> train, test = train_test_split(coordinates, data[0], None,
    ...                                random_state=0)
    >>> print("Coordinates:", train[0], test[0], sep='\n  ')
    Coordinates:
      (array([3, 1, 0]), array([-1, -3, -4]))
      (array([2]), array([-2]))
    >>> print("Data:", train[1], test[1], sep='\n  ')
    Data:
      (array([7, 3, 1]),)
      (array([5]),)
    >>> print("Weights:", train[2], test[2], sep='\n  ')
    Weights:
      (None,)
      (None,)

    """
    args = check_fit_input(coordinates, data, weights, unpack=False)
    ndata = args[1][0].size
    indices = np.arange(ndata)
    split = next(ShuffleSplit(n_splits=1, **kwargs).split(indices))
    train, test = (tuple(select(i, index) for i in args) for index in split)
    return train, test


def cross_val_score(estimator, coordinates, data, weights=None, cv=None, client=None):
    """
    Score an estimator/gridder using cross-validation.

    Similar to :func:`sklearn.model_selection.cross_val_score` but modified to
    accept spatial multi-component data with weights.

    By default, will use :class:`sklearn.model_selection.KFold` to split the
    dataset. Another cross-validation class can be passed in through the *cv*
    argument.

    Can optionally run in parallel using `dask <https://dask.pydata.org/>`__.
    To do this, pass in a :class:`dask.distributed.Client` as the *client*
    argument. Tasks in this function will be submitted to the dask cluster,
    which can be local. In this case, the resulting scores won't be the actual
    values but :class:`dask.distributed.Future` objects. Call their
    ``.result()`` methods to get back the values or pass them along to other
    dask computations.

    Parameters
    ----------
    estimator : verde gridder
        Any verde gridder class that has the ``fit`` and ``score`` methods.
    coordinates : tuple of arrays
        Arrays with the coordinates of each data point. Should be in the
        following order: (easting, northing, vertical, ...).
    data : array or tuple of arrays
        the data values of each data point. If the data has more than one
        component, *data* must be a tuple of arrays (one for each component).
    weights : none or array or tuple of arrays
        if not none, then the weights assigned to each data point. If more than
        one data component is provided, you must provide a weights array for
        each data component (if not none).
    cv : None or cross-validation generator
        Any scikit-learn cross-validation generator. Defaults to
        :class:`sklearn.model_selection.KFold`.
    client : None or dask.distributed.Client
        If None, then computations are run serially. Otherwise, should be a
        dask ``Client`` object. It will be used to dispatch computations to the
        dask cluster.

    Returns
    -------
    scores : array
        Array of scores for each split of the cross-validation generator. If
        *client* is not None, then the scores will be futures.

    Examples
    --------

    >>> from verde import grid_coordinates, Trend
    >>> coords = grid_coordinates((0, 10, -10, -5), spacing=0.1)
    >>> data = 10 - coords[0] + 0.5*coords[1]
    >>> # A linear trend should perfectly predict this data
    >>> scores = cross_val_score(Trend(degree=1), coords, data)
    >>> print(', '.join(['{:.2f}'.format(score) for score in scores]))
    1.00, 1.00, 1.00, 1.00, 1.00

    To run parallel, we need to create a :class:`dask.distributed.Client`. It will
    create a local cluster if no arguments are given so we can run the scoring on a
    single machine. We'll use threads instead of processes for this example but in most
    cases you'll want processes.

    >>> from dask.distributed import Client
    >>> client = Client(processes=False)
    >>> # The scoring will now only submit tasks to our local cluster
    >>> scores = cross_val_score(Trend(degree=1), coords, data, client=client)
    >>> # The scores are not the actual values but Futures
    >>> type(scores[0])
    <class 'distributed.client.Future'>
    >>> # We need to call .result() to get back the actual value
    >>> print('{:.2f}'.format(scores[0].result()))
    1.00
    >>> # Close the client and shutdown the local cluster
    >>> client.close()

    """
    coordinates, data, weights = check_fit_input(
        coordinates, data, weights, unpack=False
    )
    if client is None:
        client = DummyClient()
    if cv is None:
        cv = KFold(shuffle=True, random_state=0, n_splits=5)
    ndata = data[0].size
    args = (coordinates, data, weights)
    scores = []
    for train, test in cv.split(np.arange(ndata)):
        train_data, test_data = (
            tuple(select(i, index) for i in args) for index in (train, test)
        )
        score = client.submit(fit_score, estimator, train_data, test_data)
        scores.append(score)
    return np.asarray(scores)


def fit_score(estimator, train_data, test_data):
    """
    Fit an estimator on the training data and then score it on the testing data
    """
    estimator.fit(*train_data)
    return estimator.score(*test_data)


def select(arrays, index):
    """
    Index each array in a tuple of arrays.

    If the arrays tuple contains a ``None``, the entire tuple will be returned
    as is.

    Parameters
    ----------
    arrays : tuple of arrays
    index : array
        An array of indices to select from arrays.

    Returns
    -------
    indexed_arrays : tuple of arrays

    Examples
    --------

    >>> import numpy as np
    >>> select((np.arange(5), np.arange(-3, 2, 1)), [1, 3])
    (array([1, 3]), array([-2,  0]))
    >>> select((None, None, None, None), [1, 2])
    (None, None, None, None)

    """
    if arrays is None or any(i is None for i in arrays):
        return arrays
    return tuple(i.ravel()[index] for i in arrays)
