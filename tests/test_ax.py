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
    app=Node(AXMainWindow=window)
    ax=MagicMock();ax.AXIsProcessTrusted.return_value=True
    ax.AXUIElementCreateApplication.return_value=app
    ax.AXUIElementCopyAttributeValue.side_effect=lambda node,name,unused:(0,node.attrs.get(name))
    ax.AXValueGetValue.return_value=(True,SimpleNamespace(y=10))
    ax.AXUIElementPerformAction.return_value=0
    cocoa=MagicMock();running=MagicMock();running.bundleIdentifier.return_value='net.whatsapp.WhatsApp'
    cocoa.NSWorkspace.sharedWorkspace.return_value.runningApplications.return_value=[running]
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
    cocoa.NSWorkspace.sharedWorkspace.return_value.runningApplications.return_value=[]
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
        with pytest.raises(QuizError):scroll_pixels(reader,180)
        different=MagicMock();different.processIdentifier.return_value=-1
        cocoa.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value=different
        with pytest.raises(QuizError):scroll_pixels(reader,180)
    table.attrs['AXSize']=None
    with pytest.raises(QuizError):table_center(reader,table)
    table.attrs['AXSize']=2;size.width=0
    with pytest.raises(QuizError):table_center(reader,table)


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
