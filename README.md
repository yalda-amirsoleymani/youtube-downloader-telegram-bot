# How to install

This project is using `pipenv` for manage virtual enviroment.
Because it's not possible to specify multiple version of python in `Pipfile`,
`[requires]` section needs to be removed. Therefore it's necessary to specify
your prefered version of python when creating virtual enviroment. Minimum
required Python is `3.7`.

## Initial `pipenv`

```
pipenv --python VERSION
```

Replace `VERSION` with your Python version, for example:

```
pipenv --python 3.8
```

## Activate the enviroment

```
pipenv shell
```

## Install dependencies

```
pipenv install --skip-lock
```

**Note**: Shouldn't keep `Pipfile.lock` in version control if multiple
versions of Python are being targeted.
