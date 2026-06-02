"""验证 epub_meta 解析:标题/作者/出版社/ISBN/封面/损坏文件兜底"""
import io
import zipfile

import pytest

from epub_meta import (
    cover_ext_from_mime,
    extract_epub_metadata,
)


# ---------- 构造合成 EPUB 的辅助 ----------

CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _opf(meta_inner, manifest_inner=""):
    """生成最小可用的 OPF XML"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    {meta_inner}
  </metadata>
  <manifest>
    {manifest_inner}
  </manifest>
</package>
"""


def _build_epub(opf_xml, extra_files=None):
    """打包成 EPUB(zip) BytesIO"""
    extra_files = extra_files or {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype 按规范应为 STORED(无压缩)
        zf.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf_xml)
        for path, data in extra_files.items():
            zf.writestr(path, data)
    buf.seek(0)
    return buf


# ---------- 字段提取 ----------

def test_extract_basic_metadata():
    opf = _opf("""
      <dc:title>挪威的森林</dc:title>
      <dc:creator>村上春树</dc:creator>
      <dc:publisher>上海译文出版社</dc:publisher>
      <dc:language>zh-CN</dc:language>
      <dc:date>2007-07-01</dc:date>
      <dc:description>青春小说</dc:description>
      <dc:identifier opf:scheme="ISBN">9787532742691</dc:identifier>
    """)
    meta = extract_epub_metadata(_build_epub(opf))
    assert meta["title"] == "挪威的森林"
    assert meta["author"] == "村上春树"
    assert meta["publisher"] == "上海译文出版社"
    assert meta["language"] == "zh-CN"
    assert meta["date"] == "2007-07-01"
    assert meta["description"] == "青春小说"
    assert meta["isbn"] == "9787532742691"


def test_extract_multiple_creators_joined():
    """多个 dc:creator 应用顿号连接"""
    opf = _opf("""
      <dc:title>合集</dc:title>
      <dc:creator>作者甲</dc:creator>
      <dc:creator>作者乙</dc:creator>
      <dc:creator>作者丙</dc:creator>
    """)
    meta = extract_epub_metadata(_build_epub(opf))
    assert meta["author"] == "作者甲、作者乙、作者丙"


def test_date_year_only_normalized():
    """只有年份的 date 应补齐为 YYYY-01-01"""
    opf = _opf('<dc:title>x</dc:title><dc:creator>y</dc:creator><dc:date>1990</dc:date>')
    meta = extract_epub_metadata(_build_epub(opf))
    assert meta["date"] == "1990-01-01"


def test_isbn_normalization_strips_hyphens():
    """带连字符的 ISBN 应被规整为纯数字"""
    opf = _opf("""
      <dc:title>t</dc:title><dc:creator>a</dc:creator>
      <dc:identifier opf:scheme="ISBN">978-7-5327-4269-1</dc:identifier>
    """)
    meta = extract_epub_metadata(_build_epub(opf))
    assert meta["isbn"] == "9787532742691"


def test_isbn_fallback_when_scheme_missing():
    """identifier 没有 scheme,但 text 像 ISBN 时也应识别"""
    opf = _opf("""
      <dc:title>t</dc:title><dc:creator>a</dc:creator>
      <dc:identifier>9787532742691</dc:identifier>
    """)
    meta = extract_epub_metadata(_build_epub(opf))
    assert meta["isbn"] == "9787532742691"


def test_description_html_stripped():
    """description 中的 HTML 标签应被剥离"""
    opf = _opf("""
      <dc:title>t</dc:title><dc:creator>a</dc:creator>
      <dc:description>&lt;p&gt;一段&lt;b&gt;描述&lt;/b&gt;&lt;/p&gt;</dc:description>
    """)
    meta = extract_epub_metadata(_build_epub(opf))
    assert meta["description"] == "一段描述"


# ---------- 封面提取(三条识别路径) ----------

PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8cf00000003000100c8b5e3340000000049454e44ae"
    "426082"
)


def test_cover_via_epub2_meta_name_cover():
    """EPUB 2: <meta name='cover' content='cover-id'>"""
    opf = _opf(
        meta_inner="""
        <dc:title>t</dc:title><dc:creator>a</dc:creator>
        <meta name="cover" content="cover-img"/>
        """,
        manifest_inner="""
        <item id="cover-img" href="cover.png" media-type="image/png"/>
        """,
    )
    meta = extract_epub_metadata(_build_epub(opf, {"OEBPS/cover.png": PNG_1x1}))
    assert meta["cover_image_bytes"] == PNG_1x1
    assert meta["cover_mime"] == "image/png"


def test_cover_via_epub3_properties():
    """EPUB 3: manifest item properties='cover-image'"""
    opf = _opf(
        meta_inner="<dc:title>t</dc:title><dc:creator>a</dc:creator>",
        manifest_inner='<item id="c" href="cover.png" media-type="image/png" properties="cover-image"/>',
    )
    meta = extract_epub_metadata(_build_epub(opf, {"OEBPS/cover.png": PNG_1x1}))
    assert meta["cover_image_bytes"] == PNG_1x1


def test_cover_via_filename_fallback():
    """既无 meta name=cover 也无 properties=cover-image,文件名含 cover 兜底"""
    opf = _opf(
        meta_inner="<dc:title>t</dc:title><dc:creator>a</dc:creator>",
        manifest_inner='<item id="c" href="my-cover-pic.png" media-type="image/png"/>',
    )
    meta = extract_epub_metadata(_build_epub(opf, {"OEBPS/my-cover-pic.png": PNG_1x1}))
    assert meta["cover_image_bytes"] == PNG_1x1


def test_no_cover_returns_none():
    opf = _opf("<dc:title>t</dc:title><dc:creator>a</dc:creator>")
    meta = extract_epub_metadata(_build_epub(opf))
    assert meta["cover_image_bytes"] is None
    assert meta["cover_mime"] is None


# ---------- 兜底:损坏文件 / 缺字段 ----------

def test_corrupt_zip_returns_empty_dict():
    """完全不是 zip 的 bytes,不应抛异常"""
    meta = extract_epub_metadata(io.BytesIO(b"not a zip file at all"))
    assert meta["title"] == ""
    assert meta["cover_image_bytes"] is None


def test_missing_container_returns_empty():
    """zip 里没 container.xml"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("random.txt", "hi")
    buf.seek(0)
    meta = extract_epub_metadata(buf)
    assert meta["title"] == ""


def test_invalid_opf_xml_returns_empty():
    """OPF 解析失败也应平滑兜底"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", "<<< not valid xml >>>")
    buf.seek(0)
    meta = extract_epub_metadata(buf)
    assert meta["title"] == ""


# ---------- 辅助函数 ----------

@pytest.mark.parametrize("mime,expected", [
    ("image/jpeg", "jpg"),
    ("image/png", "png"),
    ("image/gif", "gif"),
    ("image/webp", "webp"),
    (None, "bin"),
    ("application/octet-stream", "bin"),
])
def test_cover_ext_from_mime(mime, expected):
    assert cover_ext_from_mime(mime) == expected
