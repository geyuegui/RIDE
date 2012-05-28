#  Copyright 2008-2012 Nokia Siemens Networks Oyj
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org:licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from wx.lib.pubsub import Publisher as WxPublisher
import inspect
import messagetype
import sys
import traceback

from robotide import utils


class RideMessage(object):
    """Base class for all messages sent by RIDE.

    :CVariables:
      topic
        Topic of this message. If not overridden, value is got from the class
        name by lowercasing it, separating words with a dot and dropping possible
        ``Message`` from the end. For example classes ``MyExample`` and
        ``AnotherExampleMessage`` get titles ``my.example`` and
        ``another.example``, respectively.
      data
        Names of attributes this message provides. These must be given as
        keyword arguments to `__init__` when an instance is created.
    """
    __metaclass__ = messagetype.messagetype
    topic = None
    data = []

    def __init__(self, **kwargs):
        """Initializes message based on given keyword arguments.

        Names of the given keyword arguments must match to names in `data`
        class attribute, otherwise the initialization fails.

        Must be called explicitly by subclass if overridden.
        """
        if sorted(kwargs.keys()) != sorted(self.data):
            raise TypeError('Argument mismatch, expected: %s' % self.data)
        self.__dict__.update(kwargs)

    def publish(self):
        """Publishes the message.

        All listeners that have subscribed to the topic of this message will be
        called with the this instance as an argument.

        Notifications are sent sequentially. Due to the limitations of current
        implementation, if any of the listeners raises an exception, subsequent
        listeners will not get the notification.
        """
        try:
            self._publish(self)
        except Exception, err:
            self._publish(RideLogException(message='Error in publishing message: ' + str(err),
                                           exception=err, level='ERROR'))

    def _publish(self, msg):
        WxPublisher().sendMessage(msg.topic, msg)


class RideLog(RideMessage):
    """This class represents a general purpose log message.

    Subclasses of this be may used to inform error conditions or to provide
    some kind of debugging information.
    """
    data = ['message', 'level', 'timestamp']


class RideLogMessage(RideLog):
    """This class represents a general purpose log message.

    This message may used to inform error conditions or to provide
    some kind of debugging information.
    """
    data = ['message', 'level', 'timestamp']

    def __init__(self, message, level='INFO'):
        """Initializes a RIDE log message.

        The log ``level`` has default value ``INFO`` and the ``timestamp``
        is generated automatically.
        """
        RideMessage.__init__(self, message=message, level=level,
                             timestamp=utils.get_timestamp())


class RideLogException(RideLog):
    """This class represents a general purpose log message with a traceback
    appended to message text. Also the original exception is included with
    the message.

    This message may used to inform error conditions or to provide
    some kind of debugging information.
    """
    data = ['message', 'level', 'timestamp', 'exception']

    def __init__(self, message, exception, level='INFO'):
        """Initializes a RIDE log exception.

        The log ``level`` has default value ``INFO`` and the ``timestamp``
        is generated automatically. Message is automatically appended with
        a traceback.
        """
        exc_type, exc_value, exc_traceback = sys.exc_info()
        if exc_traceback:
            tb = traceback.extract_tb(exc_traceback)
            message += '\n\nTraceback (most recent call last):\n%s\n%s' % (unicode(exception) ,''.join(traceback.format_list(tb)))
        RideMessage.__init__(self, message=message, level=level,
                             timestamp=utils.get_timestamp(),
                             exception=exception)


class RideInputValidationError(RideMessage):
    """Sent whenever user input is invalid."""
    data = ['message']


class RideModificationPrevented(RideMessage):
    """Sent whenever modifying command is prevented for some reason"""
    data = ['controller']


class RideSettingsChanged(RideMessage):
    """Sent when settings are changed

    keys is a tuple of key names. For example, if the "Colors" section
    was modified the keys would be ("Colors"), or a specific plugin
    setting might be ("Plugin", "Preview", "format").
    """
    data = ['keys']


class  RideTreeSelection(RideMessage):
    """Sent whenever user selects a node from the tree."""
    data = ['node', 'item', 'silent']

class RideTestExecutionStarted(RideMessage):
    """Sent whenever new test execution is started."""
    data = ['results']

class RideTestSelectedForRunningChanged(RideMessage):
    """Sent whenever user (un)selects a test from the tree for running."""
    data = ['item', 'running']

class RideTestRunning(RideMessage):
    """Sent whenever RIDE is starting to run a test case."""
    data = ['item']

class RideTestPassed(RideMessage):
    """Sent whenever RIDE has executed a test case and it passed."""
    data = ['item']

class RideTestFailed(RideMessage):
    """Sent whenever RIDE has executed a test case and it failed."""
    data = ['item']

class RideNotebookTabChanging(RideMessage):
    """Sent when the notebook tab change has started.

    Subscribing to this event allows the listener to do something before the
    tab has actually changed in the UI.
    """
    data = ['oldtab', 'newtab']


class RideNotebookTabChanged(RideMessage):
    """Sent after the notebook tab change has completed."""


class RideSaving(RideMessage):
    """Sent when user selects Save from File menu or via shortcut.

    This is used for example to store current changes from editor to data
    model, to guarantee that all changes are really saved."""
    data = ['path', 'datafile']


class RideSaved(RideMessage):
    """Sent after the file has been actually saved to disk."""
    data = ['path']


class RideSaveAll(RideMessage):
    """Sent when user selects ``Save All`` from ``File`` menu or via shortcut."""


class RideDataDirtyCleared(RideMessage):
    """Sent when datafiles dirty marking is cleared

    datafile has been saved and datafile in memory equals the serialized one.
    """
    data = ['datafile']


class RideNewProject(RideMessage):
    """Sent when a new project has been created."""
    data = ['path', 'datafile']


class RideClosing(RideMessage):
    """Sent when user selects ``Quit`` from ``File`` menu or via shortcut."""
    pass


class RideOpenSuite(RideMessage):
    """Sent when a new suite has finished loading."""
    data = ['path', 'datafile']


class RideOpenResource(RideMessage):
    """Sent when a new resource has finished loading."""
    data = ['path', 'datafile']


class RideSelectResource(RideMessage):
    """Sent when a resource should be selected."""
    data = ['item']


class RideDataChanged(RideMessage):
    """Base class for all messages notifying that data in model has changed."""


class RideFileNameChanged(RideDataChanged):
    """Sent after test case or resource file is renamed"""
    data = ['datafile', 'old_filename']


class RideDataFileRemoved(RideDataChanged):
    data = ['path', 'datafile']


class RideSuiteAdded(RideDataChanged):
    data = ['parent', 'suite']


class RideInitFileRemoved(RideDataChanged):
    data = ['path', 'datafile']


class RideImportSetting(RideDataChanged):
    """Base class for all messages about changes to import settings."""


class RideImportSettingAdded(RideImportSetting):
    """Sent whenever an import setting is added.

    ``datafile`` is the suite or resource file whose imports have changed,
    ``type`` is either ``resource``, ``library``, or ``variables``.
    """
    data = ['datafile', 'type', 'name']


class RideImportSettingChanged(RideImportSetting):
    """Sent whenever a value of import setting is changed.

    ``datafile`` is the suite or resource file whose imports have changed,
    ``type`` is either ``resource``, ``library``, or ``variables``.
    """
    data = ['datafile', 'type', 'name']


class RideImportSettingRemoved(RideImportSetting):
    """Sent whenever a value of import setting is removed.

    ``datafile`` is the suite or resource file whose imports have removed,
    ``type`` is either ``resource``, ``library``, or ``variables``.
    """
    data = ['datafile', 'type', 'name']


class RideDataChangedToDirty(RideDataChanged):
    """Sent when datafile changes from serialized version"""
    data = ['datafile']


class RideDataFileSet(RideDataChanged):
    """Set when a whole datafile is replaced with new one in a controller
    """
    data = ['item']


class RideUserKeyword(RideDataChanged):
    """Base class for all messages about changes to any user keyword."""


class RideUserKeywordAdded(RideUserKeyword):
    """Sent when a new user keyword is added to a suite or resource."""
    data = ['datafile', 'name', 'item']


class RideUserKeywordRemoved(RideUserKeyword):
    """Sent when a user keyword is removed from a suite or resource."""
    data = ['datafile', 'name', 'item']


class RideItem(RideDataChanged):
    """Base class for all messages about changes to any data item."""
    data = ['item']


class RideItemStepsChanged(RideItem):
    """"""


class RideItemNameChanged(RideItem):
    """"""


class RideItemSettingsChanged(RideItem):
    """"""


class RideTestCaseAdded(RideDataChanged):
    """Sent when a new test case is added to a suite."""
    data = ['datafile', 'name', 'item']


class RideTestCaseRemoved(RideDataChanged):
    """Sent when a test case is removed from a suite."""
    data = ['datafile', 'name', 'item']


class RideItemMovedUp(RideDataChanged):
    """Sent when an item (test, keyword, variable) is moved up."""
    data = ['item']


class RideItemMovedDown(RideDataChanged):
    """Sent when an item (test, keyword, variable) is moved down."""
    data = ['item']


class RideVariableAdded(RideDataChanged):
    """Sent when a new variable is added to a suite."""
    data = ['datafile', 'name', 'item']


class RideVariableRemoved(RideDataChanged):
    """Sent when a variable is removed from a suite."""
    data = ['datafile', 'name', 'item']


class RideVariableMovedUp(RideItemMovedUp):
    """Sent when a variable is moved up"""


class RideVariableMovedDown(RideItemMovedDown):
    """Sent when a variable is moved down"""


class RideVariableUpdated(RideDataChanged):
    """Sent when the state of a variable is changed"""
    data = ['item']


__all__ = [ name for name, cls in globals().items()
            if inspect.isclass(cls) and issubclass(cls, RideMessage) ]
