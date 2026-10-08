import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import pytest
from quiz_app.ax_reader import AXReader
from quiz_app.ax_sender import AXSender,unique
from quiz_app.errors import QuizError

class Node:
    def __init__(self,**attrs):self.attrs=attrs

@pytest.fixture
def bridge():
    bubble=Node(AXIdentifier='WAMessageBubbleTableViewCell',AXDescription='Message from Camille, !r Paris, 09:00, Received in Test',AXPosition=10)
    heading=Node(AXRole='AXHeading',AXDescription='Today')
    header=Node(AXIdentifier='NavigationBar_HeaderViewButton',AXDescription='Test')
    table=Node(AXIdentifier='ChatMessagesTableView',AXChildren=[heading,bubble])
    window=Node(AXChildren=[header,table])
    app=Node(AXMainWindow=window,AXFrontmost=True)
    ax=MagicMock();ax.AXIsProcessTrusted.return_value=True
    ax.AXUIElementCreateApplication.return_value=app
    ax.AXUIElementCopyAttributeValue.side_effect=lambda node,name,unused:(0,node.attrs.get(name))
    ax.AXValueGetValue.return_value=(True,SimpleNamespace(y=10))
    ax.AXUIElementPerformAction.return_value=0
    cocoa=MagicMock();running=MagicMock();running.bundleIdentifier.return_value='net.whatsapp.WhatsApp'
    cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_.return_value=[running]
    cocoa.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value=running
    quartz=MagicMock();quartz.CGSessionCopyCurrentDictionary.return_value={'kCGSSessionOnConsoleKey':True}
    with patch('quiz_app.ax_reader.import_module',side_effect=lambda name:ax if name=='ApplicationServices' else cocoa),patch('quiz_app.scrolling.import_module',return_value=quartz):
        yield ax,cocoa,app,window,table,bubble,header

def test_reader(bridge):
    ax,cocoa,app,window,table,bubble,header=bridge
    reader=AXReader('Test',2)
    assert reader.page()[0].author=='Camille'
    assert reader.raw_page()==[(bubble.attrs['AXDescription'],10.)]
    assert reader.attr(app,'absent') is None
    ax.AXUIElementCopyAttributeValue.return_value=(1,None)
    ax.AXUIElementCopyAttributeValue.side_effect=None
    assert reader.attr(app,'AXMainWindow') is None

def test_reader_init_errors(bridge):
    ax,cocoa,*_=bridge
    ax.AXIsProcessTrusted.return_value=False
    with pytest.raises(QuizError):AXReader('Test')
    ax.AXIsProcessTrusted.return_value=True
    cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_.return_value=[]
    with pytest.raises(QuizError):AXReader('Test')

def test_reader_safety(bridge):
    ax,cocoa,app,window,table,bubble,header=bridge
    reader=AXReader('Test')
    window.attrs['AXModal']=True
    with pytest.raises(QuizError):reader.require_group()
    window.attrs['AXModal']=False
    header.attrs['AXDescription']='Wrong'
    with pytest.raises(QuizError):reader.require_group()
    header.attrs['AXDescription']='Test'
    window.attrs['AXChildren']=[table]
    with pytest.raises(QuizError):reader.require_group()
    window.attrs['AXChildren']=[header,table]
    with patch('quiz_app.ax_reader.time.monotonic',side_effect=[0,9]):
        with pytest.raises(QuizError):reader.walk(window)
    bubble.attrs['AXDescription']='Your reaction 👍'
    assert reader.page()==[]
    bubble.attrs['AXDescription']='Message from Camille, !r Paris, 09:00, Received in Test'
    bubble.attrs['AXPosition']=None
    with pytest.raises(QuizError):reader.page()
    bubble.attrs['AXPosition']=10
    ax.AXValueGetValue.return_value=(False,None)
    with pytest.raises(QuizError):reader.page()

def test_scroll(bridge):
    ax,cocoa,app,window,table,bubble,header=bridge
    reader=AXReader('Test',2)
    with patch('quiz_app.ax_reader.time.sleep'),patch('quiz_app.ax_reader.scroll_pixels'):
        assert reader.older() is False
    with patch('quiz_app.ax_reader.scroll_pixels'),patch('quiz_app.ax_reader.time.sleep'):
        assert reader.scroll('x') is False
        reader.latest()
    with patch.object(reader,'scroll',return_value=True):
        with pytest.raises(QuizError):reader.latest()

@pytest.fixture
def sender(bridge):
    ax,cocoa,app,window,table,bubble,header=bridge
    reader=AXReader('Test');sender=AXSender(reader)
    return sender,reader,bridge

def test_press_unique(sender):
    sender,reader,bridge=sender
    node=Node(AXEnabled=False)
    assert unique([node],'one') is node
    for rows in ([],[node,node]):
        with pytest.raises(QuizError):unique(rows,'one')
    with pytest.raises(QuizError):sender.press(node)
    node.attrs['AXEnabled']=True
    sender.press(node)
    bridge[0].AXUIElementPerformAction.return_value=1
    with pytest.raises(QuizError):sender.press(node)

def test_menu(sender):
    sender,reader,(ax,cocoa,app,*_)=sender
    entry=Node(AXRole='AXMenuItem',AXTitle='Send')
    heading=Node(AXTitle='Chat',AXChildren=[entry]);bar=Node(AXChildren=[heading]);app.attrs['AXMenuBar']=bar
    sender.menu(('Chat',),('Send',))
    assert ax.AXUIElementPerformAction.call_args.args[1]=='AXCancel'
    entry.attrs['AXTitle']='Other'
    with pytest.raises(QuizError):sender.menu(('Chat',),('Send',))

def test_clipboard(sender):
    sender,reader,(ax,cocoa,app,*_)=sender
    board=cocoa.NSPasteboard.generalPasteboard.return_value
    original=MagicMock();original.types.return_value=['text','empty'];original.dataForType_.side_effect=lambda kind: b'text' if kind=='text' else None
    board.pasteboardItems.return_value=[original]
    assert len(sender.clipboard_copy())==1
    composer=Node(AXValue='hello');app.attrs['AXFocusedUIElement']=composer
    board.changeCount.return_value=2
    with patch.object(sender,'menu'),patch('quiz_app.ax_sender.time.sleep'),patch('quiz_app.ax_sender.click_control'):
        sender.paste(composer,'hello')
        assert board.writeObjects_.called
        composer.attrs['AXValue']='wrong'
        with pytest.raises(QuizError):sender.paste(composer,'hello')
        board.pasteboardItems.return_value=[];composer.attrs['AXValue']='hello'
        sender.paste(composer,'hello')
        board.changeCount.side_effect=[2,3]
        sender.paste(composer,'hello')
        app.attrs['AXFocusedUIElement']=None
        with pytest.raises(QuizError):sender.paste(composer,'hello')

def test_send(sender):
    sender,reader,(ax,cocoa,app,window,table,bubble,header)=sender
    composer=Node(AXIdentifier='ChatBar_ComposerTextView',AXValue='draft')
    window.attrs['AXChildren'].append(composer)
    with pytest.raises(QuizError):sender.send('hi','MARKER')
    composer.attrs['AXValue']=''
    window.attrs['AXChildren'].append(Node(AXIdentifier='ChatBar_SendButton',AXEnabled=True))
    with patch.object(sender,'paste'),patch.object(sender,'menu'),patch('quiz_app.ax_sender.click_control') as click,patch('quiz_app.ax_sender.time.sleep'):
        with pytest.raises(QuizError):sender.send('hi','MARKER')
        table.attrs['AXChildren'].append(Node(AXIdentifier='WAMessageBubbleTableViewCell',AXPosition=20,AXDescription='Your message, hi MARKER, 09:00, Sent to Test, Delivered'))
        ax.AXValueGetValue.side_effect=lambda value,kind,unused:(True,SimpleNamespace(y=value))
        sender.send('hi','MARKER')
        assert click.call_count==2
        window.attrs['AXChildren'][-1].attrs['AXEnabled']=False
        with pytest.raises(QuizError,match='disabled'):sender.publish('hi','MARKER')


def test_pixel_geometry_and_foreground(sender):
    from quiz_app.scrolling import scroll_pixels,table_center
    sender,reader,(ax,cocoa,app,window,table,bubble,header)=sender
    table.attrs.update(AXPosition=1,AXSize=2)
    point=SimpleNamespace(x=10,y=20);size=SimpleNamespace(width=200,height=100)
    ax.AXValueGetValue.side_effect=lambda value,kind,unused:(True,point if value==1 else size)
    quartz=MagicMock();quartz.CGSessionCopyCurrentDictionary.return_value={'kCGSSessionOnConsoleKey':True}
    cocoa.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value=reader.running
    with patch('quiz_app.scrolling.import_module',return_value=quartz),patch('quiz_app.scrolling.time.sleep'):
        scroll_pixels(reader,180)
        assert quartz.CGEventSetLocation.call_args.args[1]==(110.,70.)
        quartz.CGEventCreateScrollWheelEvent.return_value=None
        with pytest.raises(QuizError):scroll_pixels(reader,180)
        cocoa.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value=None
        app.attrs['AXFrontmost']=None
        with pytest.raises(QuizError):scroll_pixels(reader,180)
        different=MagicMock();different.processIdentifier.return_value=-1
        cocoa.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value=different
        app.attrs['AXFrontmost']=False
        with pytest.raises(QuizError):scroll_pixels(reader,180)
    table.attrs['AXSize']=None
    with pytest.raises(QuizError):table_center(reader,table)
    table.attrs['AXSize']=2;size.width=0
    with pytest.raises(QuizError):table_center(reader,table)


def test_foreground_uses_live_ax_instead_of_cached_workspace(sender):
    from quiz_app.scrolling import ensure_foreground,require_front
    sender,reader,(ax,cocoa,app,*_)=sender
    workspace=cocoa.NSWorkspace.sharedWorkspace.return_value
    workspace.frontmostApplication.return_value=None
    ensure_foreground(reader)
    require_front(reader)
    workspace.frontmostApplication.assert_not_called()
    app.attrs['AXFrontmost']=False
    workspace.frontmostApplication.return_value=reader.running
    with pytest.raises(QuizError):require_front(reader)
    app.attrs['AXFrontmost']=None
    with pytest.raises(QuizError):ensure_foreground(reader)


def test_foreground_waits_for_confirmed_activation(sender):
    from quiz_app.scrolling import ensure_foreground
    sender,reader,(ax,cocoa,app,*_)=sender
    app.attrs['AXFrontmost']=False
    calls=[]
    def activated(date):
        calls.append(date)
        if len(calls)==3:app.attrs['AXFrontmost']=True
    with patch('quiz_app.scrolling.time.sleep',side_effect=activated):
        ensure_foreground(reader)
    assert len(calls)==3


def test_raw_position(sender):
    sender,reader,(ax,cocoa,app,window,table,bubble,header)=sender
    bubble.attrs['AXPosition']=None
    assert reader.raw_position(bubble) is None
    bubble.attrs['AXPosition']=10;ax.AXValueGetValue.return_value=(False,None)
    assert reader.raw_position(bubble) is None


def test_native_identity_and_reuse(sender):
    sender,reader,(ax,cocoa,app,window,table,bubble,header)=sender
    first=reader.page()[0]
    duplicate=Node(**bubble.attrs)
    second=reader.parse_row(duplicate,'Today')[1]
    assert first.body==second.body and first.native_id!=second.native_id
    assert reader.page()[0].fingerprint==first.fingerprint
    bubble.attrs['AXDescription']='Message from Camille, !r London, 09:00, Received in Test'
    from quiz_app.history import reconcile
    with pytest.raises(QuizError):reconcile([first],reader.page())


def test_native_hash_collision_and_cell_jump(sender):
    sender,reader,(ax,cocoa,app,window,table,bubble,header)=sender
    first=reader.page()[0]
    identity=reader.identities[hash(bubble)]
    reader.identities[hash(bubble)]=(object(),*identity[1:])
    with pytest.raises(QuizError):reader.page()
    reader.identities[hash(bubble)]=identity
    jumped=reader.identify(bubble,first,1000)
    assert jumped.native_id!=first.native_id


def test_console_click_safety(sender):
    from quiz_app.scrolling import ensure_foreground,click_control
    sender,reader,(ax,cocoa,app,window,table,bubble,header)=sender
    quartz=MagicMock();quartz.CGSessionCopyCurrentDictionary.return_value={'kCGSSessionOnConsoleKey':True}
    table.attrs.update(AXPosition=1,AXSize=2)
    ax.AXValueGetValue.side_effect=lambda value,kind,unused:(True,SimpleNamespace(x=0,y=0) if value==1 else SimpleNamespace(width=100,height=100))
    with patch('quiz_app.scrolling.import_module',return_value=quartz),patch('quiz_app.scrolling.time.sleep'):
        click_control(reader,table)
        assert quartz.CGEventPost.call_count==5
        quartz.CGEventCreateMouseEvent.side_effect=[None,None,None,None]
        with pytest.raises(QuizError):click_control(reader,table)
        for session in [None,{'CGSSessionScreenIsLocked':True},{'kCGSSessionOnConsoleKey':False}]:
            quartz.CGSessionCopyCurrentDictionary.return_value=session
            with pytest.raises(QuizError):ensure_foreground(reader)


def test_directional_marks_in_native_menus(sender):
    sender,reader,(ax,cocoa,app,*_)=sender
    entry=Node(AXRole='AXMenuItem',AXTitle='\u200eSend\u200f')
    heading=Node(AXTitle='\u200eChat',AXChildren=[entry])
    app.attrs['AXMenuBar']=Node(AXChildren=[heading])
    sender.menu(('Chat',),('Send',))
    assert ax.AXUIElementPerformAction.call_args.args[1]=='AXCancel'


def test_deferred_group_check_and_automatic_selection(bridge):
    ax,cocoa,app,window,table,bubble,header=bridge
    header.attrs['AXDescription']='Another conversation'
    reader=AXReader('Test',require_active=False)
    assert reader.table is None
    sender=AXSender(reader)
    search=Node(AXIdentifier='TokenizedSearchBar_TextView',AXValue='previous search')
    result=Node(AXIdentifier='ChatListSearchView_ChatResult',AXDescription='Test')
    partial=Node(AXIdentifier='ChatListSearchView_ChatResult',AXDescription='Test extra')
    message=Node(AXIdentifier='Other',AXDescription='Test')
    draft=Node(AXIdentifier='ChatBar_ComposerTextView',AXValue='Keep my draft')
    window.attrs['AXChildren'] += [search,partial,message,draft]
    def reveal(seconds):
        if seconds==0.2 and result not in window.attrs['AXChildren']:
            window.attrs['AXChildren'].append(result)
    def select(node,action):
        assert node is result and action=='AXPress'
        header.attrs['AXDescription']='Test'
        return 0
    ax.AXUIElementPerformAction.side_effect=select
    with patch.object(sender,'paste') as paste,patch('quiz_app.ax_sender.time.sleep',side_effect=reveal):
        sender.open_group()
        paste.assert_called_once_with(search,'Test',replace=True)
    assert reader.table is table
    assert draft.attrs['AXValue']=='Keep my draft'
    with patch.object(sender,'paste'),patch('quiz_app.ax_sender.time.sleep'),patch('quiz_app.ax_sender.click_control'):
        with pytest.raises(QuizError,match='existing draft'):sender.publish('message','marker')


def test_group_search_rejects_missing_duplicate_and_wrong_header(sender):
    sender,reader,(ax,cocoa,app,window,table,bubble,header)=sender
    search=Node(AXIdentifier='TokenizedSearchBar_TextView',AXValue='')
    window.attrs['AXChildren'].append(search)
    with patch.object(sender,'paste'),patch('quiz_app.ax_sender.time.sleep'),patch.object(sender,'press') as press:
        with pytest.raises(QuizError,match='exactly one'):sender.open_group()
        press.assert_not_called()
        result=Node(AXIdentifier='ChatListSearchView_ChatResult',AXDescription='Test')
        window.attrs['AXChildren'] += [result,Node(**result.attrs)]
        with pytest.raises(QuizError,match='exactly one'):sender.open_group()
        press.assert_not_called()
        window.attrs['AXChildren'].pop()
        header.attrs['AXDescription']='Wrong'
        with pytest.raises(QuizError,match='exact requested'):sender.open_group()
        press.assert_called_once_with(result)
        window.attrs['AXModal']=True
        with pytest.raises(QuizError,match='dialog'):sender.window_nodes()
        app.attrs['AXMainWindow']=None
        with pytest.raises(QuizError,match='unavailable'):sender.open_group()


def test_search_paste_replaces_only_focused_field(sender):
    sender,reader,(ax,cocoa,app,*_)=sender
    search=Node(AXValue='old query');app.attrs['AXFocusedUIElement']=search
    board=cocoa.NSPasteboard.generalPasteboard.return_value
    board.pasteboardItems.return_value=[]
    def edit(headings,entries):
        if 'Paste' in entries:search.attrs['AXValue']='Test'
    with patch.object(sender,'menu',side_effect=edit) as menu,patch('quiz_app.ax_sender.time.sleep'):
        sender.paste(search,'Test',replace=True)
        assert menu.call_args_list[0].args[1]==('Select All','Tout sélectionner','Sélectionner tout')
        search.attrs['AXValue']=''
        menu.reset_mock()
        sender.paste(search,'Test',replace=True)
        assert menu.call_count==1
        def lose_focus(*args):app.attrs['AXFocusedUIElement']=None
        menu.side_effect=lose_focus
        with pytest.raises(QuizError,match='lost focus'):sender.paste(search,'Test',replace=True)


def test_launch_attaches_after_delayed_process_and_window(bridge):
    ax,cocoa,app,window,*_=bridge
    lookup=cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_
    running=lookup.return_value[0]
    lookup.side_effect=[[],[],[running]]
    app.attrs['AXMainWindow']=None
    sleeps=[]
    def ready(seconds):
        sleeps.append(seconds)
        if len(sleeps)==3:app.attrs['AXMainWindow']=window
    with patch('quiz_app.ax_reader.subprocess.run') as launch,patch('quiz_app.ax_reader.time.sleep',side_effect=ready):
        reader=AXReader('Test',require_active=False,launch=True)
    assert reader.running is running
    assert launch.call_args.args[0]==['/usr/bin/open','-b','net.whatsapp.WhatsApp']
    assert launch.call_args.kwargs=={'check':True,'timeout':10,'capture_output':True}
    assert sleeps==[0.2,0.1,0.2]


def test_launch_keeps_existing_ready_process(bridge):
    with patch('quiz_app.ax_reader.subprocess.run') as launch,patch('quiz_app.ax_reader.time.sleep'):
        reader=AXReader('Test',launch=True)
        assert reader.page()[0].author=='Camille'
        launch.assert_not_called()


def test_process_lookup_ignores_stale_workspace_and_finds_restarted_app(bridge):
    ax,cocoa,*_=bridge
    lookup=cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_
    original=lookup.return_value[0]
    replacement=MagicMock()
    replacement.processIdentifier.return_value=54321
    workspace=cocoa.NSWorkspace.sharedWorkspace.return_value
    workspace.runningApplications.return_value=[]
    lookup.side_effect=[[original],[replacement]]
    assert AXReader('Test',require_active=False).running is original
    assert AXReader('Test',require_active=False).running is replacement
    workspace.runningApplications.assert_not_called()
    assert lookup.call_count==2
    lookup.assert_called_with('net.whatsapp.WhatsApp')


def test_reopen_closed_window(bridge):
    ax,cocoa,app,window,*_=bridge
    app.attrs['AXMainWindow']=None
    def opened(*args,**kwargs):app.attrs['AXMainWindow']=window
    with patch('quiz_app.ax_reader.subprocess.run',side_effect=opened) as launch,patch('quiz_app.ax_reader.time.sleep'):
        reader=AXReader('Test',launch=True)
        assert reader.table is not None
        launch.assert_called_once()


@pytest.mark.parametrize('error', [OSError('missing launcher'),subprocess.CalledProcessError(1,['open']),subprocess.TimeoutExpired(['open'],10)])
def test_launch_errors_classified(bridge,error):
    lookup=bridge[1].NSRunningApplication.runningApplicationsWithBundleIdentifier_
    lookup.return_value=[]
    with patch('quiz_app.ax_reader.subprocess.run',side_effect=error),patch('quiz_app.ax_reader.time.sleep'):
        with pytest.raises(QuizError,match='Could not launch') as failure:
            AXReader('Test',require_active=False,launch=True)
        assert failure.value.code=='WHATSAPP_UNAVAILABLE'


def test_launch_timeouts_and_ambiguous_processes(bridge):
    ax,cocoa,app,window,*_=bridge
    lookup=cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_
    running=lookup.return_value[0]
    with patch('quiz_app.ax_reader.subprocess.run') as launch,patch('quiz_app.ax_reader.time.sleep'):
        lookup.return_value=[]
        with pytest.raises(QuizError,match='process unavailable'):AXReader('Test',launch=True)
        assert launch.call_count==1
        lookup.return_value=[running,running]
        with pytest.raises(QuizError,match='ambiguous'):AXReader('Test',launch=True)
        assert launch.call_count==1
        lookup.return_value=[running]
        app.attrs['AXMainWindow']=None
        with pytest.raises(QuizError,match='did not become accessible'):AXReader('Test',launch=True)


def test_launch_checks_permissions_and_locked_session_before_open(bridge):
    ax,cocoa,*_=bridge
    cocoa.NSRunningApplication.runningApplicationsWithBundleIdentifier_.return_value=[]
    with patch('quiz_app.ax_reader.subprocess.run') as launch,patch('quiz_app.ax_reader.time.sleep'):
        ax.AXIsProcessTrusted.return_value=False
        with pytest.raises(QuizError,match='Accessibility'):AXReader('Test',launch=True)
        ax.AXIsProcessTrusted.return_value=True
        quartz=MagicMock();quartz.CGSessionCopyCurrentDictionary.return_value={'CGSSessionScreenIsLocked':True}
        with patch('quiz_app.scrolling.import_module',return_value=quartz):
            with pytest.raises(QuizError,match='unlocked'):AXReader('Test',launch=True)
        launch.assert_not_called()


def test_operator_stop_prevents_native_send_at_each_guard(sender):
    sender,reader,(ax,cocoa,app,window,*_)=sender
    sender.cancel_requested=lambda:True
    with pytest.raises(QuizError,match='Arrêt'):sender.open_group()
    with pytest.raises(QuizError,match='Arrêt'):sender.publish('Message','private')
    composer=Node(AXIdentifier='ChatBar_ComposerTextView',AXValue='')
    button=Node(AXIdentifier='ChatBar_SendButton',AXEnabled=True)
    window.attrs['AXChildren'] += [composer,button]
    with patch.object(sender,'paste') as paste,patch('quiz_app.ax_sender.click_control') as click,patch('quiz_app.ax_sender.time.sleep'):
        calls=iter([False,True]);sender.cancel_requested=lambda:next(calls)
        with pytest.raises(QuizError,match='Arrêt'):sender.publish('Message','private')
        paste.assert_not_called();click.assert_not_called()
        calls=iter([False,False,True]);sender.cancel_requested=lambda:next(calls)
        with pytest.raises(QuizError,match='Arrêt'):sender.publish('Message','private')
        paste.assert_called_once();click.assert_not_called()
