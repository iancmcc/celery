from __future__ import absolute_import
from __future__ import with_statement

import errno
import signal
import sys

from mock import Mock, patch

from celery.bin.celeryd_multi import (
    main,
    MultiTool,
    findsig,
    abbreviations,
    parse_ns_range,
    format_opt,
    quote,
    NamespacedOptionParser,
    multi_args,
    __doc__ as doc,
)

from celery.tests.utils import Case, WhateverIO


class test_functions(Case):

    def test_findsig(self):
        self.assertEqual(findsig(["a", "b", "c", "-1"]), 1)
        self.assertEqual(findsig(["--foo=1", "-9"]), 9)
        self.assertEqual(findsig(["-INT"]), signal.SIGINT)
        self.assertEqual(findsig([]), signal.SIGTERM)
        self.assertEqual(findsig(["-s"]), signal.SIGTERM)
        self.assertEqual(findsig(["-log"]), signal.SIGTERM)

    def test_abbreviations(self):
        expander = abbreviations({"%s": "START",
                                  "%x": "STOP"})
        self.assertEqual(expander("foo%s"), "fooSTART")
        self.assertEqual(expander("foo%x"), "fooSTOP")
        self.assertEqual(expander("foo%y"), "foo%y")
        self.assertIsNone(expander(None))

    def test_parse_ns_range(self):
        self.assertEqual(parse_ns_range("1-3", True), ['1', '2', '3'])
        self.assertEqual(parse_ns_range("1-3", False), ['1-3'])
        self.assertEqual(parse_ns_range("1-3,10,11,20", True),
                ['1', '2', '3', '10', '11', '20'])

    def test_format_opt(self):
        self.assertEqual(format_opt("--foo", None), "--foo")
        self.assertEqual(format_opt("-c", 1), "-c 1")
        self.assertEqual(format_opt("--log", "foo"), "--log=foo")

    def test_quote(self):
        self.assertEqual(quote("the 'quick"), "'the '\\''quick'")


class test_NamespacedOptionParser(Case):

    def test_parse(self):
        x = NamespacedOptionParser(["-c:1,3", "4"])
        self.assertEqual(x.namespaces.get("1,3"), {"-c": "4"})
        x = NamespacedOptionParser(["-c:jerry,elaine", "5",
                                    "--loglevel:kramer=DEBUG",
                                    "--flag",
                                    "--logfile=foo", "-Q", "bar", "a", "b",
                                    "--", ".disable_rate_limits=1"])
        self.assertEqual(x.options, {"--logfile": "foo",
                                     "-Q": "bar",
                                     "--flag": None})
        self.assertEqual(x.values, ["a", "b"])
        self.assertEqual(x.namespaces.get("jerry,elaine"), {"-c": "5"})
        self.assertEqual(x.namespaces.get("kramer"), {"--loglevel": "DEBUG"})
        self.assertEqual(x.passthrough, "-- .disable_rate_limits=1")


class test_multi_args(Case):

    @patch("socket.gethostname")
    def test_parse(self, gethostname):
        p = NamespacedOptionParser(["-c:jerry,elaine", "5",
                                    "--loglevel:kramer=DEBUG",
                                    "--flag",
                                    "--logfile=foo", "-Q", "bar", "jerry",
                                    "elaine", "kramer",
                                    "--", ".disable_rate_limits=1"])
        it = multi_args(p, cmd="COMMAND", append="*AP*",
                prefix="*P*", suffix="*S*")
        names = list(it)
        self.assertEqual(names[0][0:2], ('*P*jerry*S*',
            [
                'COMMAND', '-n *P*jerry*S*', '-Q bar',
                '-c 5', '--flag', '--logfile=foo',
                '-- .disable_rate_limits=1', '*AP*',
            ]
        ))
        self.assertEqual(names[1][0:2], ('*P*elaine*S*',
            [
                'COMMAND', '-n *P*elaine*S*', '-Q bar',
                '-c 5', '--flag', '--logfile=foo',
                '-- .disable_rate_limits=1', '*AP*',
            ]
        ))
        self.assertEqual(names[2][0:2], ('*P*kramer*S*',
            [
                'COMMAND', '--loglevel=DEBUG', '-n *P*kramer*S*',
                '-Q bar', '--flag', '--logfile=foo',
                '-- .disable_rate_limits=1', '*AP*',
            ]
        ))
        expand = names[0][2]
        self.assertEqual(expand("%h"), "*P*jerry*S*")
        self.assertEqual(expand("%n"), "jerry")
        names2 = list(multi_args(p, cmd="COMMAND", append="",
                prefix="*P*", suffix="*S*"))
        self.assertEqual(names2[0][1][-1], '-- .disable_rate_limits=1')

        gethostname.return_value = 'example.com'
        p2 = NamespacedOptionParser(["10", "-c:1", "5"])
        names3 = list(multi_args(p2, cmd="COMMAND"))
        self.assertEqual(len(names3), 10)
        self.assertEqual(names3[0][0:2], ('celery1.example.com',
            ['COMMAND', '-n celery1.example.com', '-c 5', '']))
        for i, worker in enumerate(names3[1:], 2):
            self.assertEqual(worker[0:2], ('celery%s.example.com' % i,
                ['COMMAND', '-n celery%s.example.com' % i, '']))

        names4 = list(multi_args(p2, cmd="COMMAND", suffix='""'))
        self.assertEqual(len(names4), 10)
        self.assertEqual(names4[0][0:2], ('celery1',
            ['COMMAND', '-n celery1', '-c 5', '']))

        p3 = NamespacedOptionParser(["foo", "-c:foo", "5"])
        names5 = list(multi_args(p3, cmd="COMMAND", suffix='""'))
        self.assertEqual(names5[0][0:2], ('foo',
            ['COMMAND', '-n foo', '-c 5', '']))


class test_MultiTool(Case):

    def setUp(self):
        self.fh = WhateverIO()
        self.env = {}
        self.t = MultiTool(env=self.env, fh=self.fh)

    def test_note(self):
        self.t.note("hello world")
        self.assertEqual(self.fh.getvalue(), "hello world\n")

    def test_note_quiet(self):
        self.t.quiet = True
        self.t.note("hello world")
        self.assertFalse(self.fh.getvalue())

    def test_info(self):
        self.t.verbose = True
        self.t.info("hello info")
        self.assertEqual(self.fh.getvalue(), 'hello info\n')

    def test_info_not_verbose(self):
        self.t.verbose = False
        self.t.info("hello info")
        self.assertFalse(self.fh.getvalue())

    def test_error(self):
        self.t.say = Mock()
        self.t.usage = Mock()
        self.assertEqual(self.t.error("foo"), 1)
        self.t.say.assert_called_with("foo")
        self.t.usage.assert_called_with()

        self.t.say = Mock()
        self.assertEqual(self.t.error(), 1)
        self.assertFalse(self.t.say.called)

        self.assertEqual(self.t.retcode, 1)

    @patch("celery.bin.celeryd_multi.Popen")
    def test_waitexec(self, Popen):
        self.t.note = Mock()
        pipe = Popen.return_value = Mock()
        pipe.wait.return_value = -10
        self.assertEqual(self.t.waitexec(["-m", "foo"], "path"), 10)
        Popen.assert_called_with(['path', '-m', 'foo'], env=self.t.env)
        self.t.note.assert_called_with("* Child was terminated by signal 10")

        pipe.wait.return_value = 2
        self.assertEqual(self.t.waitexec(["-m", "foo"], "path"), 2)
        self.t.note.assert_called_with(
                "* Child terminated with failure code 2")

        pipe.wait.return_value = 0
        self.assertFalse(self.t.waitexec(["-m", "foo", "path"]))

    def test_nosplash(self):
        self.t.nosplash = True
        self.t.splash()
        self.assertFalse(self.fh.getvalue())

    def test_splash(self):
        self.t.nosplash = False
        self.t.splash()
        self.assertIn("celeryd-multi", self.fh.getvalue())

    def test_usage(self):
        self.t.usage()
        self.assertTrue(self.fh.getvalue())

    def test_help(self):
        self.t.help([])
        self.assertIn(doc, self.fh.getvalue())

    def test_expand(self):
        self.t.expand(['foo%n', 'ask', 'klask', 'dask'])
        self.assertEqual(self.fh.getvalue(),
                "fooask\nfooklask\nfoodask\n")

    def test_restart(self):
        stop = self.t._stop_nodes = Mock()
        self.t.restart(['jerry', 'george'], "celeryd")
        waitexec = self.t.waitexec = Mock()
        self.assertTrue(stop.called)
        callback = stop.call_args[1]["callback"]
        self.assertTrue(callback)

        waitexec.return_value = 0
        callback("jerry", ["arg"], 13)
        waitexec.assert_called_with(["arg"])
        self.assertIn("OK", self.fh.getvalue())
        self.fh.seek(0)
        self.fh.truncate()

        waitexec.return_value = 1
        callback("jerry", ["arg"], 13)
        self.assertIn("FAILED", self.fh.getvalue())

    def test_stop(self):
        self.t.getpids = Mock()
        self.t.getpids.return_value = [2, 3, 4]
        self.t.shutdown_nodes = Mock()
        self.t.stop(["a", "b", "-INT"], "celeryd")
        self.t.shutdown_nodes.assert_called_with(
            [2, 3, 4], sig=signal.SIGINT, retry=None, callback=None,

        )

    def test_kill(self):
        self.t.getpids = Mock()
        self.t.getpids.return_value = [
            ("a", None, 10),
            ("b", None, 11),
            ("c", None, 12)
        ]
        sig = self.t.signal_node = Mock()

        self.t.kill(["a", "b", "c"], "celeryd")

        sigs = sig.call_args_list
        self.assertEqual(len(sigs), 3)
        self.assertEqual(sigs[0][0], ("a", 10, signal.SIGKILL))
        self.assertEqual(sigs[1][0], ("b", 11, signal.SIGKILL))
        self.assertEqual(sigs[2][0], ("c", 12, signal.SIGKILL))

    def prepare_pidfile_for_getpids(self, PIDFile):
        class pids(object):

            def __init__(self, path):
                self.path = path

            def read_pid(self):
                try:
                    return {"celeryd@foo.pid": 10,
                            "celeryd@bar.pid": 11}[self.path]
                except KeyError:
                    raise ValueError()
        PIDFile.side_effect = pids

    @patch("celery.bin.celeryd_multi.PIDFile")
    @patch("socket.gethostname")
    def test_getpids(self, gethostname, PIDFile):
        gethostname.return_value = "e.com"
        self.prepare_pidfile_for_getpids(PIDFile)
        callback = Mock()

        p = NamespacedOptionParser(["foo", "bar", "baz"])
        nodes = self.t.getpids(p, "celeryd", callback=callback)
        self.assertEqual(nodes, [
            ('foo.e.com',
              ('celeryd', '--pidfile=celeryd@foo.pid', '-n foo.e.com', ''),
             10),
            ('bar.e.com',
              ('celeryd', '--pidfile=celeryd@bar.pid', '-n bar.e.com', ''),
             11),
        ])
        self.assertTrue(callback.called)
        callback.assert_called_with(
            "baz.e.com",
            ['celeryd', '--pidfile=celeryd@baz.pid', '-n baz.e.com', ''],
            None,
        )
        self.assertIn("DOWN", self.fh.getvalue())

        # without callback, should work
        nodes = self.t.getpids(p, "celeryd", callback=None)

    @patch("celery.bin.celeryd_multi.PIDFile")
    @patch("socket.gethostname")
    @patch("celery.bin.celeryd_multi.sleep")
    def test_shutdown_nodes(self, slepp, gethostname, PIDFile):
        gethostname.return_value = "e.com"
        self.prepare_pidfile_for_getpids(PIDFile)
        self.assertIsNone(self.t.shutdown_nodes([]))
        self.t.signal_node = Mock()
        self.t.node_alive = Mock()
        self.t.node_alive.return_value = False

        callback = Mock()
        self.t.stop(["foo", "bar", "baz"], "celeryd", callback=callback)
        sigs = self.t.signal_node.call_args_list
        self.assertEqual(len(sigs), 2)
        self.assertEqual(sigs[0][0], ("foo.e.com", 10, signal.SIGTERM))
        self.assertEqual(sigs[1][0], ("bar.e.com", 11, signal.SIGTERM))
        self.t.signal_node.return_value = False
        self.assertTrue(callback.called)
        self.t.stop(["foo", "bar", "baz"], "celeryd", callback=None)
        calls = [0]

        def on_node_alive(pid):
            calls[0] += 1
            if calls[0] > 3:
                return True
            return False
        self.t.signal_node.return_value = True
        self.t.node_alive.side_effect = on_node_alive
        self.t.stop(["foo", "bar", "baz"], "celeryd", retry=True)

    @patch("os.kill")
    def test_node_alive(self, kill):
        kill.return_value = True
        self.assertTrue(self.t.node_alive(13))
        esrch = OSError()
        esrch.errno = errno.ESRCH
        kill.side_effect = esrch
        self.assertFalse(self.t.node_alive(13))
        kill.assert_called_with(13, 0)

        enoent = OSError()
        enoent.errno = errno.ENOENT
        kill.side_effect = enoent
        with self.assertRaises(OSError):
            self.t.node_alive(13)

    @patch("os.kill")
    def test_signal_node(self, kill):
        kill.return_value = True
        self.assertTrue(self.t.signal_node("foo", 13, 9))
        esrch = OSError()
        esrch.errno = errno.ESRCH
        kill.side_effect = esrch
        self.assertFalse(self.t.signal_node("foo", 13, 9))
        kill.assert_called_with(13, 9)
        self.assertIn("Could not signal foo", self.fh.getvalue())

        enoent = OSError()
        enoent.errno = errno.ENOENT
        kill.side_effect = enoent
        with self.assertRaises(OSError):
            self.t.signal_node("foo", 13, 9)

    def test_start(self):
        self.t.waitexec = Mock()
        self.t.waitexec.return_value = 0
        self.assertFalse(self.t.start(["foo", "bar", "baz"], "celeryd"))

        self.t.waitexec.return_value = 1
        self.assertFalse(self.t.start(["foo", "bar", "baz"], "celeryd"))

    def test_show(self):
        self.t.show(["foo", "bar", "baz"], "celeryd")
        self.assertTrue(self.fh.getvalue())

    @patch("socket.gethostname")
    def test_get(self, gethostname):
        gethostname.return_value = "e.com"
        self.t.get(["xuzzy.e.com", "foo", "bar", "baz"], "celeryd")
        self.assertFalse(self.fh.getvalue())
        self.t.get(["foo.e.com", "foo", "bar", "baz"], "celeryd")
        self.assertTrue(self.fh.getvalue())

    @patch("socket.gethostname")
    def test_names(self, gethostname):
        gethostname.return_value = "e.com"
        self.t.names(["foo", "bar", "baz"], "celeryd")
        self.assertIn("foo.e.com\nbar.e.com\nbaz.e.com", self.fh.getvalue())

    def test_execute_from_commandline(self):
        start = self.t.commands["start"] = Mock()
        self.t.error = Mock()
        self.t.execute_from_commandline(["multi", "start", "foo", "bar"])
        self.assertFalse(self.t.error.called)
        start.assert_called_with(["foo", "bar"], "celeryd")

        self.t.error = Mock()
        self.t.execute_from_commandline(["multi", "frob", "foo", "bar"])
        self.t.error.assert_called_with("Invalid command: frob")

        self.t.error = Mock()
        self.t.execute_from_commandline(["multi"])
        self.t.error.assert_called_with()

        self.t.error = Mock()
        self.t.execute_from_commandline(["multi", "-foo"])
        self.t.error.assert_called_with()

        self.t.execute_from_commandline(["multi", "start", "foo",
                "--nosplash", "--quiet", "-q", "--verbose", "--no-color"])
        self.assertTrue(self.t.nosplash)
        self.assertTrue(self.t.quiet)
        self.assertTrue(self.t.verbose)
        self.assertTrue(self.t.no_color)

    def test_stop_verify(self):
        self.t._stop_nodes = Mock()
        self.t.stop_verify(["foo", "bar", "baz"], "celeryd")
        self.assertEqual(self.t._stop_nodes.call_args[1]["retry"], 2)

    @patch("celery.bin.celeryd_multi.MultiTool")
    def test_main(self, MultiTool):
        m = MultiTool.return_value = Mock()
        with self.assertRaises(SystemExit):
            main()
        m.execute_from_commandline.assert_called_with(sys.argv)
