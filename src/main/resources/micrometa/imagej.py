"""ImageJ related stuff like reading measurement results, etc."""

# NOTE: consider creating a generic superclass for macro templates, providing
# the methods required for all templates and derived subclasses that contain a
# required method that adds the specific variables-setting code.

from os import listdir
from os.path import join, dirname, basename, splitext

from . import __version__
from .iotools import readtxt
from .log import LOG as log
from .pathtools import exists


def gen_tile_config(mosaic_ds):
    """Generate a tile configuration for Fiji's stitcher.

    Generate a layout configuration file for a ceartain mosaic in the format
    readable by Fiji's "Grid/Collection stitching" plugin. The configuration is
    stored in a file in the input directory carrying the mosaic's index number
    as a suffix.

    Parameters
    ----------
    mosaic_ds : micrometa.dataset.MosaicData
        The mosaic dataset to generate the tile config for.

    Returns
    -------
    config : list(str)
        The tile configuration as a list of strings, one per line.
    """
    conf = list()
    conf.append('# Generated by %s (%s).\n#\n' % (__name__, __version__))
    subvol_size_z = mosaic_ds.subvol[0].get_dimensions()['Z']
    subvol_position_dim = len(mosaic_ds.subvol[0].position['relative'])
    conf.append('# Define the number of dimensions we are working on\n')
    if subvol_size_z > 1:
        conf.append('dim = 3\n')
        if subvol_position_dim < 3:
            coord_format = '(%f, %f, 0.0)\n'
        else:
            coord_format = '(%f, %f, %f)\n'
    else:
        conf.append('dim = 2\n')
        coord_format = '(%f, %f)\n'
    conf.append('# Define the image coordinates (in pixels)\n')
    log.debug("Mosaic storage path: %s", mosaic_ds.storage['path'])
    for vol in mosaic_ds.subvol:
        vol_fname = vol.storage['full']
        # convert path to subvolumes to be relative to mosaic file:
        if vol_fname.startswith(mosaic_ds.storage['path']):
            vol_fname = vol_fname[len(mosaic_ds.storage['path']):]
        line = '%s; ; ' % vol_fname
        # always use forward slashes as path separator (works on all OS!)
        line = line.replace('\\', '/')
        line += coord_format % vol.position['relative']
        conf.append(line)
    return conf


def write_tile_config(mosaic_ds, outdir='', padlen=0):
    """Generate and write the tile configuration file.

    Call the function to generate the corresponding tile configuration and
    store the result in a file. The naming scheme is "mosaic_xyz.txt" where
    "xyz" is the zero-padded index number of this particular mosaic.

    Parameters
    ----------
    mosaic_ds : dataset.MosaicData
        The mosaic dataset to write the tile config for.
    outdir : str
        The output directory, if empty the input directory is used.
    padlen : int
        An optional padding length for the index number used in the resulting
        file name, e.g. '2' will result in names like 'mosaic_01.txt' and so on.
    """
    log.info('write_tile_config(%i)', mosaic_ds.supplement['index'])
    config = gen_tile_config(mosaic_ds)
    fname = 'mosaic_%0' + str(padlen) + 'i.txt'
    fname = fname % mosaic_ds.supplement['index']
    if outdir == '':
        fname = join(mosaic_ds.storage['path'], fname)
    else:
        fname = join(outdir, fname)
    out = open(fname, 'w')
    out.writelines(config)
    out.close()
    log.warn('Wrote tile config to %s', out.name)


def write_all_tile_configs(experiment, outdir=''):
    """Wrapper to generate all TileConfiguration.txt files.

    All arguments are directly passed on to write_tile_config().
    """
    padlen = len(str(len(experiment)))
    log.debug("Padding tile configuration file indexes to length %i", padlen)
    for mosaic_ds in experiment:
        write_tile_config(mosaic_ds, outdir, padlen)


def locate_templates(tplpath=''):
    """Locate path to templates, possibly in a .zip or .jar file."""
    # by default templates are expected in a subdir of the current package:
    if tplpath == '':
        tplpath = join(dirname(__file__), 'ijm_templates')
        log.debug('Looking for template directory: %s', tplpath)
        if not exists(tplpath):
            tplpath += '.zip'
            log.debug('Looking for template directory: %s', tplpath)
    # extended magic to look for templates in jar files having a version number
    # (and possibly a 'SNAPSHOT' part in their filename) without having to
    # hard-code those strings here:
    if tplpath.lower().endswith('.jar'):
        candidates = list()
        jar_dir = dirname(tplpath)
        jar_basename = basename(splitext(tplpath)[0])
        for candidate in listdir(jar_dir):
            if candidate.startswith(jar_basename):
                log.debug('Found potential jar for templates: [%s]', candidate)
                candidates.append(candidate)
        candidates.sort()
        log.info('Identified jar for templates: [%s]', candidates[-1])
        tplpath = join(jar_dir, candidates[-1])

    if not exists(tplpath):
        raise IOError("Templates location can't be found!")
    log.info('Templates location: %s', tplpath)
    return tplpath


def gen_stitching_macro_code(experiment, pfx, path='', tplpath='', opts={}):
    """Generate code in ImageJ's macro language to stitch the mosaics.

    Take two template files ("head" and "body") and generate an ImageJ
    macro to stitch the mosaics. Using the splitted templates allows for
    setting default values in the head that can be overridden in this
    generator method (the ImageJ macro language doesn't have a command to
    check if a variable is set or not, it just exits with an error).

    Parameters
    ----------
    experiment : micrometa.experiment.MosaicExperiment
        The object containing all information about the mosaic.
    pfx : str
        The prefix for the two template files, will be completed with the
        corresponding suffixes "_head.ijm" and "_body.ijm".
    path : str
        The path to use as input directory *INSIDE* the macro.
    tplpath : str
        The path to a directory or zip file containing the templates.
    opts : dict (optional)
        A dict with key-value pairs to be put into the macro between the head
        and body to override the macro's default settings.
        NOTE: the values are placed literally in the macro code, this means
        that strings have to be quoted, e.g. opts['foo'] = '"bar baz"'

    Returns
    -------
    ijm : list(str) or str
        The generated macro code as a list of str (one str per line) or as
        a single long string if requested via the "flat" parameter.
    """
    # pylint: disable-msg=E1103
    #   the type of 'ijm' is not correctly inferred by pylint and it complains
    templates = locate_templates(tplpath)
    ijm = []
    ijm.append('// Generated by %s (%s).\n\n' % (__name__, __version__))
    ijm.append("// =================== BEGIN macro HEAD ===================\n")
    ijm += readtxt(pfx + '_head.ijm', templates)
    ijm.append("// ==================== END macro HEAD ====================\n")
    ijm.append('\n')

    ijm.append('name = "%s";\n' % experiment.infile['dname'])
    # windows path separator (in)sanity:
    path = path.replace('\\', '\\\\')
    ijm.append('input_dir="%s";\n' % path)
    ijm.append('use_batch_mode = true;\n')
    for option, value in opts.items():
        ijm.append('%s = %s;\n' % (option, value))

    # If the overlap is below a certain level (5 percent), we disable
    # computing the actual positions and subpixel accuracy:
    if experiment[0].get_overlap('pct') < 5.0:
        ijm.append('compute = false;\n')

    ijm.append('\n')
    ijm.append("// =================== BEGIN macro BODY ===================\n")
    ijm += readtxt(pfx + '_body.ijm', templates)
    ijm.append("// ==================== END macro BODY ====================\n")
    log.debug('--- ijm ---\n%s\n--- ijm ---', ijm)
    return ijm


def write_stitching_macro(code, fname, dname):
    """Write generated macro code into a file.

    Parameters
    ----------
    code : list(str)
        The code as a list of strings, one per line.
    fname : str
        The desired output filename.
    dname : str
        The output directory.
    """
    fname = join(dname, fname)
    log.debug('Writing macro to output directory: "%s".', fname)
    with open(fname, 'w') as out:
        out.writelines(code)
        log.warn('Wrote macro template to "%s".', out.name)
