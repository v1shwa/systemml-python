# systemml python -  1.2.0

A working version of systemml 1.2.0 python

Fixes this particular bug in python 3.6 and above.

```
    import * only allowed at module level (estimators.py, line 917)
    Traceback (most recent call last):
      File "/usr/local/lib/python3.6/site-packages/systemml/mllearn/__init__.py", line 45, in <module>
        from .estimators import *
      File "/usr/local/lib/python3.6/site-packages/systemml/mllearn/estimators.py", line 917
        def __init__(self, sparkSession, keras_model, input_shape, transferUsingDF=False, load_keras_weights=True, weights=None, labels=None, batch_size=64, max_iter=2000, test_iter=10, test_interval=500, display=100, lr_policy="step", weight_decay=5e-4, regularization_type="L2"):
        ^
    SyntaxError: import * only allowed at module level
```

## Installation

`pip install https://github.com/v1shwa/systemml-python.git`