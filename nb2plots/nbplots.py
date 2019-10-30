"""
A directive for including a matplotlib plot in a Sphinx document.

This directive is based on the ``plot`` directive of matplotlib, with thanks.

By default, in HTML output, `nbplot` will include a .png file with a
link to a high-res .png and .pdf.  In LaTeX output, it will include a
.pdf.

The source code for the plot is **inline content** to the directive:.  It can
be with or without *doctest* syntax.  Here's an example without doctest
syntax::

    .. nbplot::

        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
        import numpy as np
        img = mpimg.imread('_static/stinkbug.png')
        imgplot = plt.imshow(img)

Here's an example with doctest syntax::

    .. nbplot::

        A plotting example:
        >>> import matplotlib.pyplot as plt
        >>> plt.plot([1,2,3], [4,5,6])  #doctest: +ELLIPSIS
        [...]

Options
-------

The ``nbplot`` directive supports the following options:

    format : {'python', 'doctest'}
        Specify the format of the input.  If not specified, nbplot guesses the
        format from the content.

    include-source : bool
        Whether to display the source code. The default can be changed using
        the `nbplot_include_source` variable in ``conf.py``.  Any doctests in
        the source code will still be run by the doctest builder.
        `include-source` has the same effect as ``:hide-from: all`` then
        ``:show-to: doctest`` (in fact, that is how it is implemented).  See
        below for interactions of ``:include-source:`` and these options.

    hide-from : str
        Space-separated list of builders that should not render any source from
        this directive.  Can also be the special value "all", hiding the source
        from all builders.  Any builder names in `show-to` override builders
        specified with this option.  If you apply ``:hide-from:`` options as
        well as ``:include-source: false`` (see above), these will have no
        effect, because ``:include-source: false`` implies ``:hide-from: all``.

    show-to : str
        Space-separated list of builders that *should* render any source from
        this directive.  Builder names here override any builders specified in
        `hide-from`.  If you apply ``:show-to:`` options as well as
        ``:include-source: false`` (see above) these can enable additional
        builders on top of the implied ``doctest`` builder.

    encoding : str
        If this source file is in a non-UTF8 or non-ASCII encoding,
        the encoding must be specified using the `:encoding:` option.
        The encoding will not be inferred using the ``-*- coding -*-``
        metacomment.

    keepfigs : bool
        If specified, do not close figures from previous plot command. This
        allows you to build up a plot in stages, with the current nbplot
        command building on the figure generated by previous nbplot commands.

    nofigs : bool
        If specified, the code block will be run, but no figures will be
        inserted.  This is sometimes necessary when your code generates a plot,
        but you do not want to include it.  If the code does not generate a
        plot, this option is not necessary.

    raises : str
        String giving error class.  The code runner will assert this error was
        raised by the enclosed code, and suppress stderr.

    render-parts : str
        The contents of the directive may be divided into "parts" at lines
        containing ``.. part`` with a blank line before and after.  This option
        gives a Python expression returning an integer or tuple giving the
        indices of the *parts* that should be used for the built output of the
        code block.  These to-be-built parts can be different from the parts
        used to generate the figures associated with the block, defined in the
        ``run-parts`` option below.  The typical use is for building when
        running the ``render-parts`` would be too slow, or the building system
        does not have the requirements to run the code in ``render-parts``.
        The contents of this option is a Python expression returning an integer
        or a tuple, where an integer is the index of the part to render, and a
        tuple is a tuple of such integers. The expression operates in a
        namespace defined by the contents of the ``nbplot_flags`` config
        variable (a dict) and any extra namespace defined above this directive
        with :class:`NBPlotFlags` directives.

        Any selected parts get labeled such that the doctest builder does not
        see them, and therefore they do not get picked up by the sphinx doctest
        extension.  The nbplots extension tells the other builders to build the
        skipped doctest as if it were a standard doctest.

        Examples::

            :render-parts: 0 if have_matlab else 1

        Default value is 0.

    run-parts : str
        See ``render-parts`` above.  Python expression that returns integer or
        tuple giving indices for parts that should be executed when generating
        the figures.  Any doctests in these parts also get wrapped in standard
        doctest blocks, and so will be picked up by the sphinx doctest builder.

        Examples::

            :run-parts: 0 if slow else 1

        Default value is 0.

The namespace of the nbplot command is reset to empty for each document.  The
code in each nbplot directive instance in a given document uses the namespace
generated by previous nbplot directive instances in the same document.

Additionally, this directive supports all of the options of the
`image` directive, except for `target` (since plot will add its own
target).  These include `alt`, `height`, `width`, `scale`, `align` and
`class`.

Configuration options
---------------------

The nbplot directive has the following configuration options:

    nbplot_include_source
        Default value for the include-source option

    nbplot_pre_code
        Code that should be executed before each plot.

    nbplot_formats
        File formats to generate. List of tuples or strings::

            [(suffix, dpi), suffix, ...]

        that determine the file format and the DPI. For entries whose
        DPI was omitted, sensible defaults are chosen. When passing from
        the command line through sphinx_build the list should be passed as
        suffix:dpi,suffix:dpi, ....

    nbplot_html_show_formats
        Whether to show links to the files in HTML.

    nbplot_rcparams
        A dictionary containing any non-standard rcParams that should
        be applied at the beginning of each document.

    nbplot_working_directory
        By default, the working directory will be changed to the directory of
        the example, so the code can get at its data files, if any.  Also its
        path will be added to `sys.path` so it can import any helper modules
        sitting beside it.  This configuration option can be used to specify
        a central directory (also added to `sys.path`) where data files and
        helper modules for all code are located.  If the directory is relative,
        directory taken to be relative to root directory of the project (rather
        than source directory).

    nbplot_template
        Provide a customized template for preparing restructured text.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import six

try:
    from collections.abc import Sequence
except ImportError:
    from collections import Sequence
from collections import defaultdict
import sys, os, shutil, io, re, textwrap
from os.path import (relpath, abspath, join as pjoin, dirname, exists,
                     basename, splitext, isdir)
import traceback
from pprint import pformat

from docutils.statemachine import StringList
from docutils import nodes
from docutils.parsers.rst import directives
from docutils.parsers.rst.directives.images import Image
align = Image.align
from docutils.parsers.rst import Directive

import jinja2
def format_template(template, **kw):
    return jinja2.Template(template).render(**kw)

import matplotlib
import matplotlib.cbook as cbook
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib._pylab_helpers import Gcf

__version__ = 2


class NBPlotFlags(Directive):
    """ Set flag namespace for nbplot
    """
    has_content = True
    required_arguments = 0
    optional_arguments = 0

    def run(self):
        document = self.state.document
        env = document.settings.env
        docname = env.docname
        local_ns = env.nbplot_flag_namespaces[docname]
        six.exec_('\n'.join(self.content), None, local_ns)
        return []


class NBPlotShowFlags(Directive):
    """ Show flag namespace for nbplot

    This directive shows the result of :class:`NBPlotFlags` directives, for
    debugging and testing.
    """
    has_content = True
    required_arguments = 0
    optional_arguments = 0

    def run(self):
        document = self.state.document
        env = document.settings.env
        docname = env.docname
        local_ns = env.nbplot_flag_namespaces[docname]
        content = pformat(local_ns)
        return [nodes.literal_block(content, content)]


# Options for NBPlotDirective

def _option_boolean(arg):
    if not arg or not arg.strip():
        # no argument given, assume used as a flag
        return True
    elif arg.strip().lower() in ('no', '0', 'false'):
        return False
    elif arg.strip().lower() in ('yes', '1', 'true'):
        return True
    else:
        raise PlotValueError('"%s" unknown boolean' % arg)


def _option_format(arg):
    return directives.choice(arg, ('python', 'doctest'))


def _option_align(arg):
    return directives.choice(
        arg,
        ("top", "middle", "bottom", "left", "center", "right"))


class nbplot_container(nodes.container, nodes.Targetable):
    """ Container for rendered nbplot contents

    Also serves as a reference target.
    """

    def likes_builder(self, builder_name):
        """ Return True if attributes specify this is an acceptable build

        Parameters
        ----------
        builder_name : str
            Name of builder by which the node is being visited.

        Returns
        -------
        liked : bool
            True if node attributes are compatible with `builder_name`, False
            otherwise.
        """
        hide_from = self.get('hide-from', [])
        show_to = self.get('show-to', [])
        if builder_name in show_to:
            return True
        if 'all' in hide_from:
            return False
        return builder_name not in hide_from


class nbplot_epilogue(nodes.container, nodes.Targetable):
    """ Container for figures etc following nbplot """


class dont_doctest_block(nodes.General, nodes.FixedTextElement):
    """ Container to hide doctest block from doctest builder """


def doctest_filter(node):
    """ True if node is a ``doctest_block`` node
    """
    return isinstance(node, nodes.doctest_block)


class NBPlotDirective(Directive):
    """ Implements nbplot directive

    """ + __doc__
    has_content = True
    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {'alt': directives.unchanged,
                   'height': directives.length_or_unitless,
                   'width': directives.length_or_percentage_or_unitless,
                   'scale': directives.nonnegative_int,
                   'align': _option_align,
                   'class': directives.class_option,
                   'hide-from': directives.unchanged,
                   'show-to': directives.unchanged,
                   'include-source': _option_boolean,
                   'format': _option_format,
                   'keepfigs': directives.flag,
                   'nofigs': directives.flag,
                   'encoding': directives.encoding,
                   'raises': directives.unchanged,
                   'render-parts': directives.unchanged,
                   'run-parts': directives.unchanged,
                  }

    # Node classes for rendered, not rendered nbplot contents
    nbplot_node = nbplot_container
    nbplot_epilogue = nbplot_epilogue
    dont_doctest_block = dont_doctest_block

    def _dont_doctest_doctests(self, tree):
        """ Replace ``doctest_block`` nodes with ``dont_doctest_block`` nodes
        """
        for node in tree.traverse(doctest_filter):
            new_node = self.dont_doctest_block(node.rawsource, node.rawsource)
            node.replace_self(new_node)

    def rst2nodes(self, lines, node_class, node_attrs=None):
        """ Build docutils nodes from list of ReST strings `lines`

        Parameters
        ----------
        lines : list
            list of strings containing ReST.
        node_class : :class:`nodes.Node` class
            Container class for output
        node_attrs : None or dict, optional
            Attributes to apply to instance of `node_class`.  These simply get
            applied to the containing node, except where they signal that the
            contents should be hidden from the doctest builder, in which case
            the doctest_block nodes get swapped for similar nodes that don't
            get picked up by the doctest builder.

        Returns
        -------
        nodes : list
            A length 1 list of nodes, where contained node is of type
            `node_class` and node contents are nodes generated from ReST in
            `lines`.
        """
        node_attrs = {} if node_attrs is None else node_attrs
        text = '\n'.join(lines)
        node = node_class(text)
        for key, value in node_attrs.items():
            if value:
                node[key] = value
        self.add_name(node)
        if len(lines) != 0:
            self.state.nested_parse(StringList(lines),
                                    self.content_offset,
                                    node)
        # Implement hiding of doctests from doctest builder
        if not likes_builder(node, 'doctest'):
            self._dont_doctest_doctests(node)
        return [node]

    def _get_parts(self, option_name):
        if option_name not in self.options:
            return (0,)
        env = self.state.document.settings.env
        name_space = env.nbplot_flag_namespaces[env.docname].copy()
        indices = eval(self.options[option_name], name_space)
        return indices if isinstance(indices, Sequence) else (indices,)

    def _select_parts(self):
        parts = parse_parts(self.content)
        to_render = [parts[i]['contents']
                     for i in self._get_parts('render-parts')]
        to_run = [parts[i]['contents']
                  for i in self._get_parts('run-parts')]
        return ('\n'.join(sum(to_render, [])),
                '\n'.join(sum(to_run, [])))

    def _contains_doctest(self, multi_str):
        """ Check  ``format`` option for doctest specifier, else guess
        """
        if 'format' in self.options:
            return False if self.options['format'] == 'python' else True
        return contains_doctest(multi_str)

    def _build_epilogue(self, images, source_rel_dir, build_dir):
        """ Build the epilogue housing the image links
        """
        document = self.state.document
        config = document.settings.env.config
        nofigs = 'nofigs' in self.options

        # how to link to files from the RST file
        rst_file = document.attributes['source']
        rst_dir = dirname(rst_file)
        dest_dir_link = pjoin(relpath(setup.confdir, rst_dir),
                              source_rel_dir).replace(os.path.sep, '/')
        build_dir_link = relpath(build_dir, rst_dir).replace(os.path.sep, '/')

        images_to_show = [] if nofigs else images[:]
        n_to_show = len(images_to_show)

        opts = [':%s: %s' % (key, val)
                for key, val in self.options.items()
                if key in ('alt', 'height', 'width', 'scale', 'align',
                            'class')]

        # These are the headers for blocks in the template that link to the
        # various build plot images - where the logic is different for each
        # builder.
        only_html = ".. only:: html"
        only_latex = ".. only:: latex"
        only_texinfo = ".. only:: texinfo"

        # Build source text for image link epilogue
        epilogue_source = format_template(
            config.nbplot_template or EPILOGUE_TEMPLATE,
            dest_dir=dest_dir_link,
            build_dir=build_dir_link,
            multi_image=n_to_show > 1,
            only_html=only_html,
            only_latex=only_latex,
            only_texinfo=only_texinfo,
            options=opts,
            images=images_to_show,
            html_show_formats=config.nbplot_html_show_formats and n_to_show)

        return self.rst2nodes(epilogue_source.splitlines(),
                              self.nbplot_epilogue)

    def _copy_image_files(self, images, dest_dir):
        # copy image files to builder's output directory, if necessary
        if not exists(dest_dir):
            cbook.mkdirs(dest_dir)

        for img in images:
            for fn in img.filenames():
                destimg = pjoin(dest_dir, basename(fn))
                if fn != destimg:
                    shutil.copyfile(fn, destimg)

    def _proc_builder_opts(self, config):
        """ Process options related to later per-node selection of builders

        hide-from ad show-to options apply on top of include-source option and
        config setting.
        """
        options = self.options
        options.setdefault('include-source', config.nbplot_include_source)
        if options['include-source']:
            node_attrs = {'hide-from': [], 'show-to': []}
        else:  # include-source is False
            node_attrs = {'hide-from': ['all'], 'show-to': ['doctest']}
        for opt_name in node_attrs:
            if opt_name not in options:
                continue
            values = options[opt_name].split()
            node_attrs[opt_name] += [b_name.strip() for b_name in values]
        return node_attrs

    def run(self):
        document = self.state.document
        config = document.settings.env.config
        env = document.settings.env
        docname = env.docname

        # Check and fill options for skipping nodes per builder
        node_attrs = self._proc_builder_opts(config)

        # If this is the first directive in the document, clear context
        if env.nbplot_reset_markers.get(docname, False):
            context_reset = False
        else:
            env.nbplot_reset_markers[docname] = True
            context_reset = True
        close_figs = False if 'keepfigs' in self.options else True

        counter = document.attributes.get('_plot_counter', 0) + 1
        document.attributes['_plot_counter'] = counter

        source_file_name = document.attributes['source']
        base, ext = splitext(basename(source_file_name))
        output_base = '%s-%d' % (base, counter)
        # ensure that LaTeX includegraphics doesn't choke in foo.bar.pdf
        # filenames
        output_base = output_base.replace('.', '-')

        # should the code raise an exception?
        raises = (eval(self.options['raises']) if 'raises' in self.options
                  else None)

        # determine output directory name fragment
        source_rel_name = relpath(source_file_name, setup.confdir)
        source_rel_dir = dirname(source_rel_name)
        while source_rel_dir.startswith(os.path.sep):
            source_rel_dir = source_rel_dir[1:]

        # build_dir: where to place output files (temporarily)
        build_dir = pjoin(dirname(setup.app.doctreedir),
                          'nbplot_directive',
                          source_rel_dir)
        # get rid of .. in paths, also changes pathsep
        # see note in Python docs for warning about symbolic links on Windows.
        # need to compare source and dest paths at end
        build_dir = os.path.normpath(build_dir)

        if not exists(build_dir):
            os.makedirs(build_dir)

        # output_dir: final location in the builder's directory
        dest_dir = abspath(pjoin(setup.app.builder.outdir, source_rel_dir))
        if not exists(dest_dir):
            # no problem here for me, but just use built-ins
            os.makedirs(dest_dir)

        # We are now going to chose which parts of the text go to which
        # builders.  We might have specified which builders we want all the
        # text to go to, using the hide-from, and show-to options, or
        # (equivalently) using the include-source option. Or, we might have
        # split the code into parts, to send some of the code to the renderers,
        # such as HTML, and other parts of the code to the doctest builder
        # only.  For most builders, we do that by adding 'hide-from' and
        # 'show-to' attributes to the containing doctest node, and notifying
        # the builders visiting the node to discard the node, if those
        # attributes say they should.  However, the doctest builder does not
        # visit, so we have have to run some doctree post-processing on the
        # nbplot nodes, to check hide-from, show-to for the 'doctest' builder,
        # and, if the node should be hidden from the doctest builder, we
        # replace the doctest_block nodes with something that behaves in the
        # same way as a doctest_block node for all the visiting builders, but,
        # because it is not a doctest_block node, does not get picked up by the
        # doctest builder.

        # Break contents into parts, and select
        to_render, to_run = self._select_parts()

        # make figures
        try:
            images = render_figures(to_run,
                                    source_file_name,
                                    build_dir,
                                    output_base,
                                    config=config,
                                    context = True,  # keep plot context
                                    function_name = None,
                                    context_reset=context_reset,
                                    close_figs=close_figs,
                                    raises=raises)
            errors = []
        except PlotError as err:
            reporter = self.state.memo.reporter
            sm = reporter.system_message(
                2,
                'Exception plotting {output_base}\n'
                'from: {source_file_name}\n'
                'with code:\n\n{to_run}\n\n'
                'Exception:\n{err}'.format(**locals()),
                line=self.lineno)
            images = []
            errors = [sm]

        # generate output restructuredtext
        lines = [''] + [row.rstrip() for row in to_render.split('\n')]
        # If the code is not in doctest format, make it into code blocks.
        if not self._contains_doctest(to_render):
            lines = (['.. code-block:: python'] +
                     ['    ' + line for line in lines])
        # If we're going to run different code from the source we're rendering
        # then change node_attrs in place to hide the rendered code from the
        # doctest builder.
        if to_render != to_run:
            _hide_from_builder(node_attrs, 'doctest')
        # Build the rendered node
        rendered_nodes = self.rst2nodes(lines,
                                        self.nbplot_node,
                                        node_attrs)
        # Epilogue node contains the built figures and supporting stuff.
        epilogue = self._build_epilogue(images, source_rel_dir, build_dir)
        ret = rendered_nodes + epilogue + errors
        self._copy_image_files(images, dest_dir)
        # Now, we need to put in nodes for the code that ran, so the doctest
        # builder can find it.  But, we hide these nodes from all the other
        # builders (using hide-from all).
        if to_render != to_run and self._contains_doctest(to_run):
            lines = [''] + [row.rstrip() for row in to_run.split('\n')]
            ret += self.rst2nodes(
                lines,
                self.nbplot_node,
                {'hide-from': ['all'], 'show-to': ['doctest']})
        return ret


def _hide_from_builder(attrs, builder_name):
    """ Change ``show-to, hide-from`` values to hide from `builder_name`

    Modify `attrs` in-place.

    Parameters
    ----------
    attrs : dict
        Dict containing keys ``hide-from`` and ``show-to``.
    builder_name : str
        Name of builder that we want `attrs` to signal hiding from.
    """
    if builder_name in attrs['show-to']:
        attrs['show-to'].remove(builder_name)
    if builder_name not in attrs['hide-from']:
        attrs['hide-from'].append(builder_name)


#------------------------------------------------------------------------------
# Doctest handling
#------------------------------------------------------------------------------

def contains_doctest(text):
    try:
        # check if it's valid Python as-is
        compile(text, '<string>', 'exec')
        return False
    except SyntaxError:
        pass
    r = re.compile(r'^\s*>>>', re.M)
    m = r.search(text)
    return bool(m)


def unescape_doctest(text):
    """
    Extract code from a piece of text, which contains either Python code
    or doctests.

    """
    if not contains_doctest(text):
        return text

    code = ""
    for line in text.split("\n"):
        m = re.match(r'^\s*(>>>|\.\.\.) (.*)$', line)
        if m:
            code += m.group(2) + "\n"
        elif line.strip():
            code += "# " + line.strip() + "\n"
        else:
            code += "\n"
    return code


def remove_coding(text):
    """
    Remove the coding comment, which six.exec_ doesn't like.
    """
    sub_re = re.compile("^#\s*-\*-\s*coding:\s*.*-\*-$", flags=re.MULTILINE)
    return sub_re.sub("", text)

#------------------------------------------------------------------------------
# Template
#------------------------------------------------------------------------------


EPILOGUE_TEMPLATE = """
{{ only_html }}

   {% if html_show_formats and not multi_image %}
   (
   {%- for img in images -%}
     {%- for fmt in img.formats -%}
       {%- if not loop.first -%}, {% endif -%}
       `{{ fmt }} <{{ dest_dir }}/{{ img.basename }}.{{ fmt }}>`__
     {%- endfor -%}
   {%- endfor -%}
   )
   {% endif %}

   {% for img in images %}
   .. figure:: {{ build_dir }}/{{ img.basename }}.png
      {% for option in options -%}
      {{ option }}
      {% endfor %}

      {% if html_show_formats and multi_image -%}
        (
        {%- for fmt in img.formats -%}
        {%- if not loop.first -%}, {% endif -%}
        `{{ fmt }} <{{ dest_dir }}/{{ img.basename }}.{{ fmt }}>`__
        {%- endfor -%}
        )
      {%- endif -%}

   {% endfor %}

{{ only_latex }}

   {% for img in images %}
   {% if 'pdf' in img.formats -%}
   .. image:: {{ build_dir }}/{{ img.basename }}.pdf
   {% endif -%}
   {% endfor %}

{{ only_texinfo }}

   {% for img in images %}
   .. image:: {{ build_dir }}/{{ img.basename }}.png
      {% for option in options -%}
      {{ option }}
      {% endfor %}

   {% endfor %}

"""


# the context of the plot for all directives
plot_context = dict()


class ImageFile(object):
    def __init__(self, basename, path):
        self.basename = basename
        self.dirname = path
        self.formats = []

    def filename(self, format):
        return pjoin(self.dirname, "%s.%s" % (self.basename, format))

    def filenames(self):
        return [self.filename(fmt) for fmt in self.formats]


class PlotError(RuntimeError):
    pass


class PlotValueError(ValueError):
    pass


PARTER = re.compile(r"""(?:\n\n|^)\.\.\ part\n  # part separator
                    ((?:\ *\w+\ *=\ *.+\n)*)  # attributes
                    \n
                    """, re.VERBOSE)


ATTRIBUTER = re.compile(r'^(\w+) *= *(.+?) *$')


def _proc_part_def(part_def):
    """ Return part dictionary from `part_def` string
    """
    if part_def == '':
        return {}
    if not part_def.startswith(' '):
        raise PlotValueError('Part attributes should be indented')
    justified = textwrap.dedent(part_def).splitlines()
    if any(s.startswith(' ') for s in justified):
        raise PlotValueError('Part attributes should have same indentation')
    return dict(ATTRIBUTER.match(line).groups() for line in justified)


def _part_strs2dicts(part_strs):
    """ Return part def, contents pairs as part dictionaries
    """
    dicts = []
    while len(part_strs):
        part_dict = _proc_part_def(part_strs.pop(0))
        part_dict['contents'] = part_strs.pop(0).splitlines()
        dicts.append(part_dict)
    return dicts


def parse_parts(lines):
    """ Parse string list `content` into `parts`

    Parameters
    ----------
    lines : sequence of str
        Contents from directive.  Each element is a line.

    Returns
    -------
    parts : list
        List of dicts.  Each dict is a "part". Part dicts each have key
        ``contents``, with value being a list of strings, one string per line.
        The other key, value pairs are attributes of this part.
    """
    text = '\n'.join(lines).strip()
    part_strs = PARTER.split(text)
    if len(part_strs) == 1:
        return [{'contents': part_strs[0].splitlines()}]
    if part_strs[0] == '':  # begins with part attributes
        part_strs.pop(0)
    else:  # does not begin with part attributes, insert empty attributes
        part_strs.insert(0, '')
    return _part_strs2dicts(part_strs)


def _check_wd(path):
    try:
        abs_path = abspath(path)
    except TypeError as err:
        raise TypeError(str(err) + '\n`nbplot_working_directory` option in '
                        'Sphinx configuration file must be a string or '
                        'None')
    if not isdir(abs_path):
        raise OSError('`nbplot_working_directory` option (="{}") in '
                      'Sphinx configuration file must be a valid '
                      'directory path'.format(path))
    return abs_path


def run_code(code, code_path=None, ns=None, function_name=None, workdir=None,
             pre_code=None, raises=None):
    """
    Run `code` from file at `code_path` in namespace `ns`

    Parameters
    ----------
    code : str
        code to run.
    code_path : str
        Filename containing the code.
    ns : None or dict, optional
        Python namespace in which to execute code.  If None, make fresh
        namespace.
    function_name : None or str, optional
        If non-empty string, name of function to execute after executing
        `code`.
    workdir : None or str, optional
        Working directory in which to run code.  Defaults to current working
        directory.
    pre_code : None or str, optional
        Any code to run before `code`.
    raises : None or Exception class
        An exception that the run code should raise.

    Returns
    -------
    ns : dict
        Namespace, filled from execution of `code`.
    """
    # Change the working directory to the directory of the example, so
    # it can get at its data files, if any.  Add its path to sys.path
    # so it can import any helper modules sitting beside it.
    if six.PY2:
        pwd = os.getcwdu()
    else:
        pwd = os.getcwd()
    old_sys_path = list(sys.path)
    workdir = os.getcwd() if workdir is None else workdir
    os.chdir(workdir)
    sys.path.insert(0, workdir)

    # Reset sys.argv
    old_sys_argv = sys.argv
    sys.argv = [code_path]

    # Redirect stdout
    stdout = sys.stdout
    sys.stdout = io.StringIO() if six.PY3 else io.BytesIO()

    # Assign a do-nothing print function to the namespace.  There
    # doesn't seem to be any other way to provide a way to (not) print
    # that works correctly across Python 2 and 3.
    def _dummy_print(*arg, **kwarg):
        pass

    ns = {} if ns is None else ns
    try:
        try:
            code = unescape_doctest(code)
            if pre_code and not ns:
                six.exec_(six.text_type(pre_code), ns)
            ns['print'] = _dummy_print
            if "__main__" in code:
                six.exec_("__name__ = '__main__'", ns)
            code = remove_coding(code)
            if raises is None:
                six.exec_(code, ns)
            else:  # Code should raise exception
                try:
                    six.exec_(code, ns)
                except raises:
                    pass
            if function_name:
                six.exec_(function_name + "()", ns)
        except (Exception, SystemExit):
            raise PlotError(traceback.format_exc())
    finally:
        os.chdir(pwd)
        sys.argv = old_sys_argv
        sys.path[:] = old_sys_path
        sys.stdout = stdout
    return ns


def render_figures(code, code_path, output_dir, output_base, config,
                   context=True, function_name=None, context_reset=False,
                   close_figs=False, raises=None):
    """ Run plot code and save the hi/low res PNGs, PDF in `output_dir`

    Save the images under `output_dir` with file names derived from
    `output_base`.

    Parameters
    ----------
    code : str
        String containing code to run.
    code_path : str
        Path of file containing code.  Usually path to ``.rst`` file.
    output_dir : str
        Path to which to write output images from plots.
    output_base : str
        Prefix for filename(s) for output image(s).
    config : instance
        Sphinx configuration instance.
    context : {True, False}, optional
        If True, use persistent context (workspace) for executing code.
        Otherwise create new empty context for executing code.
    function_name : None or str, optional
        If not-empty str, name of function to execute after executing `code`.
    context_reset : {False, True}, optional
        If True, clear persistent context (workspace) for code.
    close_figs : {False, True}, optional
        If True, close all figures generated before our `code` runs.  False can
        be useful when building up a plot with several `code` blocks.
    raises : None or Exception, optional
        Exception class that code should raise, or None, for no exception.
    """
    # -- Parse format list
    default_dpi = {'png': 80, 'hires.png': 200, 'pdf': 200}
    formats = []
    plot_formats = config.nbplot_formats
    if isinstance(plot_formats, six.string_types):
        # String Sphinx < 1.3, Split on , to mimic
        # Sphinx 1.3 and later. Sphinx 1.3 always
        # returns a list.
        plot_formats = plot_formats.split(',')
    for fmt in plot_formats:
        if isinstance(fmt, six.string_types):
            if ':' in fmt:
                suffix,dpi = fmt.split(':')
                formats.append((str(suffix), int(dpi)))
            else:
                formats.append((fmt, default_dpi.get(fmt, 80)))
        elif type(fmt) in (tuple, list) and len(fmt)==2:
            formats.append((str(fmt[0]), int(fmt[1])))
        else:
            raise PlotError('invalid image format "%r" in nbplot_formats' % fmt)

    # Build the output
    ns = plot_context if context else {}

    if context_reset:
        plt.close('all')
        matplotlib.rc_file_defaults()
        matplotlib.rcParams.update(config.nbplot_rcparams)
        plot_context.clear()

    close_figs = not context or close_figs

    # Get working directory for code execution
    if setup.config.nbplot_working_directory is not None:
        workdir = _check_wd(setup.config.nbplot_working_directory)
    elif code_path is not None:
        workdir = abspath(dirname(code_path))
    else:
        workdir = None

    if close_figs:
        plt.close('all')

    run_code(code, code_path, ns, function_name, workdir=workdir,
             pre_code=setup.config.nbplot_pre_code, raises=raises)

    images = []
    fig_managers = Gcf.get_all_fig_managers()
    for j, figman in enumerate(fig_managers):
        if len(fig_managers) == 1:
            img = ImageFile(output_base, output_dir)
        else:
            img = ImageFile("%s_%02d" % (output_base, j), output_dir)
        images.append(img)
        for format, dpi in formats:
            try:
                figman.canvas.figure.savefig(img.filename(format), dpi=dpi)
            except Exception:
                raise PlotError(traceback.format_exc())
            img.formats.append(format)

    return images


# Sphinx event handlers

def _false():
    # Must be function rather than lambda to allow pickling of environment
    return False


def do_builder_init(app):
    env = app.env
    env.nbplot_reset_markers = defaultdict(_false)
    env.nbplot_flag_namespaces = defaultdict(dict)


def do_purge_doc(app, env, docname):
    """ Clear markers for whether `docname` has seen a plot context reset
    """
    env.nbplot_reset_markers[docname] = False
    env.nbplot_flag_namespaces[docname] = env.config.nbplot_flags.copy()


def likes_builder(node, builder_name):
    return (not hasattr(node, 'likes_builder') or
            node.likes_builder(builder_name))


def checked_visit(self, node):
    if not likes_builder(node, self.builder.name):
        raise nodes.SkipNode


def checked_depart(self, node):
    pass


def dont_doctest_visit(self, node):
    # Make node behave like doctest node, for builders that visit.  This allows
    # us to make another not-doctest_block node to replace the actual
    # ductest_block node, so that, for builders that visit, such as html, we
    # get the same output, but thd doctest builder passes over it, because it
    # is not a doctest_block node.
    self.visit_doctest_block(node)


def dont_doctest_depart(self, node):
    self.depart_doctest_block(node)


def setup(app):
    setup.app = app
    setup.config = app.config
    setup.confdir = app.confdir

    # Builders which run visit methods on nodes.  Basically everything but
    # doctest.
    visiting_builders = ('html', 'latex', 'text', 'texinfo')

    # Containers used as markers for nbplot contents
    for node_class in (nbplot_container, nbplot_epilogue):
        app.add_node(node_class,
                     **{builder: (checked_visit, checked_depart)
                        for builder in visiting_builders})
    # Allow nodes hidden from doctest builder to render on other builders
    app.add_node(dont_doctest_block,
                 **{builder: (dont_doctest_visit, dont_doctest_depart)
                    for builder in visiting_builders})
    app.add_directive('nbplot', NBPlotDirective)
    app.add_directive('nbplot-flags', NBPlotFlags)
    app.add_directive('nbplot-show-flags', NBPlotShowFlags)
    pre_default = "import numpy as np\nfrom matplotlib import pyplot as plt\n"
    app.add_config_value('nbplot_pre_code', pre_default, True)
    app.add_config_value('nbplot_include_source', True, True)
    app.add_config_value('nbplot_formats', ['png', 'hires.png', 'pdf'], True)
    app.add_config_value('nbplot_html_show_formats', True, True)
    app.add_config_value('nbplot_rcparams', {}, True)
    app.add_config_value('nbplot_working_directory', None, True)
    app.add_config_value('nbplot_template', None, True)
    app.add_config_value('nbplot_flags', {}, True)

    # Create dictionaries in builder environment
    app.connect(str('builder-inited'), do_builder_init)
    # Clear marker indicating that we have already started parsing a page
    app.connect(str('env-purge-doc'), do_purge_doc)
