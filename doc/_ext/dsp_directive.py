from sphinx.ext.autodoc import *
from dispatcher import Dispatcher
# noinspection PyProtectedMember
from dispatcher.draw import dsp2dot, _func_name

# ------------------------------------------------------------------------------
# Doctest handling
# ------------------------------------------------------------------------------
from doctest import DocTestParser, DocTestRunner, NORMALIZE_WHITESPACE, ELLIPSIS


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


# ------------------------------------------------------------------------------
# Auto dispatcher content
# ------------------------------------------------------------------------------


def get_summary(doc):
    while doc and not doc[0].strip():
        doc.pop(0)

    # If there's a blank line, then we can assume the first sentence /
    # paragraph has ended, so anything after shouldn't be part of the
    # summary
    for i, piece in enumerate(doc):
        if not piece.strip():
            doc = doc[:i]
            break

    # Try to find the "first sentence", which may span multiple lines
    m = re.search(r"^([A-Z].*?\.)(?:\s|$)", " ".join(doc).strip())
    if m:
        summary = m.group(1).strip()
    elif doc:
        summary = doc[0].strip()
    else:
        summary = ''

    return summary


def get_grandfather_content(content, level=2):
    if content.parent and level:
        return get_grandfather_content(content.parent, level - 1)
    return content, get_grandfather_offset(content)


def get_grandfather_offset(content):
    if content.parent:
        return get_grandfather_offset(content.parent) + content.parent_offset
    return 0


def _import_docstring(documenter):
    if getattr(documenter.directive, 'content', None):
        # noinspection PyBroadException
        try:
            import textwrap

            content = documenter.directive.content

            def get_code(source, c=''):
                s = "\n%s" % c
                return textwrap.dedent(s.join(map(str, source)))

            is_doctest = contains_doctest(get_code(content))
            offset = documenter.directive.content_offset
            if is_doctest:
                parent, parent_offset = get_grandfather_content(content)
                parent = parent[:offset + len(content) - parent_offset]
                code = get_code(parent)
            else:
                code = get_code(content, '>>> ')

            parser = DocTestParser()
            runner = DocTestRunner(verbose=0,
                                   optionflags=NORMALIZE_WHITESPACE | ELLIPSIS)

            glob = {}
            exec('import %s as mdl\n' % documenter.modname, glob)
            glob = glob['mdl'].__dict__
            tests = parser.get_doctest(code, glob, '', '', 0)
            runner.run(tests, clear_globs=False)

            documenter.object = tests.globs[documenter.name]
            documenter.code = content
            documenter.is_doctest = True
            return True
        except:
            return False


def _description(lines, dsp, documenter):
    docstring = dsp.__doc__

    if documenter.objpath:
        attr_docs = documenter.analyzer.find_attr_docs()
        key = ('.'.join(documenter.objpath[:-1]), documenter.objpath[-1])
        if key in attr_docs:
            docstring = attr_docs[key]

    if isinstance(docstring, str):
        docstring = docstring.split('\n') + ['']

    lines.extend(docstring)


def _code(lines, documenter):
    if documenter.code:
        if documenter.is_doctest:
            lines += [row.rstrip() for row in documenter.code]
        else:
            lines.extend(['.. code-block:: python', ''])
            lines.extend(['    %s' % r.rstrip() for r in documenter.code])

        lines.append('')


def _plot(lines, dsp, dot_view_opt):
    digraph = u'   %s' % dsp2dot(dsp, **dot_view_opt).source
    lines.extend(['.. graphviz::', '', digraph, ''])


def _table_heather(lines, title, dsp_name):
    q = 's' if dsp_name[-1] != 's' else ''
    lines.extend(['.. csv-table:: **%s\'%s %s**' % (dsp_name, q, title), ''])


def _data(lines, dsp):
    data = [v for v in sorted(dsp.nodes.items()) if v[1]['type'] == 'data']
    if data:
        _table_heather(lines, 'data', dsp.name)

        for k, v in data:
            link = ''
            if 'description' in v:
                des = v['description']
            else:
                # noinspection PyBroadException
                try:
                    des = k.__doc__
                    link = '%s.%s' % (k.__module__, k.__name__)
                except:
                    des = ''

            link = ':obj:`%s <%s>`' % (str(k), link)

            lines.append(u'   %s, %s' % (link, get_summary(des.split('\n'))))

        lines.append('')


def _functions(lines, dsp, function_module):
    fun = [v for v in sorted(dsp.nodes.items()) if v[1]['type'] == 'function']
    if fun:
        _table_heather(lines, 'functions', dsp.name)

        for k, v in fun:
            full_name = ''

            if 'description' in v:
                des = v['description']
            elif 'function' in v:
                des = v['function'].__doc__
            else:
                des = ''
            des = get_summary(des.split('\n'))
            if ('function' in v
                and isinstance(v['function'], (FunctionType,
                                               BuiltinFunctionType))):
                fun = v['function']
                full_name = '%s.%s' % (fun.__module__, fun.__name__)

            name = _func_name(k, function_module)

            lines.append(u'   :func:`%s <%s>`, %s' % (name, full_name, des))
        lines.append('')


# ------------------------------------------------------------------------------
# Registration hook
# ------------------------------------------------------------------------------

PLOT = object()
def _dsp2dot_option(arg):
    """Used to convert the :dmap: option to auto directives."""

    def map_args(*args, **kwargs):
        k = ['workflow', 'dot', 'edge_attr', 'view', 'level', 'function_module']
        kw = dict(zip(k, args))
        kw.update(kwargs)
        return kw
    kw = eval('map_args(%s)' % arg)

    return kw if kw else PLOT



class DispatcherDocumenter(DataDocumenter):
    """
    Specialized Documenter subclass for dispatchers.
    """

    objtype = 'dispatcher'
    directivetype = 'data'
    option_spec = dict(DataDocumenter.option_spec)
    option_spec.update({
        'description': bool_option,
        'opt': _dsp2dot_option,
        'code': bool_option,
        'data': bool_option,
        'func': bool_option,
    })
    default_opt = {
        'workflow': False,
        'dot': None,
        'edge_attr': None,
        'view': False,
        'level': 0,
        'function_module': False,
    }
    code = None
    is_doctest = False

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        return (isinstance(parent, ModuleDocumenter)
                and isinstance(member, Dispatcher))

    def add_directive_header(self, sig):
        if not self.code:
            if not self.options.annotation:
                self.options.annotation = ' = %s' % self.object.name
            super(DispatcherDocumenter, self).add_directive_header(sig)

    def import_object(self):
        if (getattr(self.directive, 'arguments', None)
            and _import_docstring(self)):
            return True
        self.is_doctest = False
        self.code = None
        return DataDocumenter.import_object(self)

    def format_signature(self):
        return ''

    def add_content(self, more_content, no_docstring=False):
        # noinspection PyUnresolvedReferences
        sourcename = self.get_sourcename()
        dsp = self.object
        opt = self.options

        dot_view_opt = {}
        dot_view_opt.update(self.default_opt)
        if opt.opt and opt.opt is not PLOT:
            dot_view_opt.update(opt.opt)

        lines = []

        if opt.code:
            _code(lines, self)

        if not opt or opt.des:
            _description(lines, dsp, self)

        if not opt or opt.opt:
            _plot(lines, dsp, dot_view_opt)

        if not opt or opt.data:
            _data(lines, dsp)

        if not opt or opt.func:
            _functions(lines, dsp, dot_view_opt['function_module'])

        for line in lines:
            self.add_line(line, sourcename)


class DispatcherDirective(AutoDirective):
    _default_flags = {'des', 'opt', 'data', 'func', 'code', 'annotation'}

    def __init__(self, *args, **kwargs):
        super(DispatcherDirective, self).__init__(*args, **kwargs)
        if args[0] == 'dispatcher':
            self.name = 'autodispatcher'


def add_autodocumenter(app, cls):
    app.debug('[app] adding autodocumenter: %r', cls)
    from sphinx.ext import autodoc

    autodoc.add_documenter(cls)
    app.add_directive('auto' + cls.objtype, DispatcherDirective)


def setup(app):
    app.setup_extension('sphinx.ext.autodoc')
    app.setup_extension('sphinx.ext.graphviz')
    add_autodocumenter(app, DispatcherDocumenter)
    app.add_directive('dispatcher', DispatcherDirective)
