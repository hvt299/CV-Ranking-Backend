import asyncio
from datetime import datetime, timezone, timedelta
from app.database.config import connect_to_mongo, close_mongo_connection
from app.repositories.blog_repository import BlogRepository
from app.services.domain.admin_service import AdminService

BLOG_POSTS = [
    {
        "title": "Cách viết CV chuẩn ATS để vượt qua vòng lọc hồ sơ tự động",
        "category": "cv_writing",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Phần lớn doanh nghiệp hiện nay dùng hệ thống ATS (Applicant Tracking System) để sàng lọc hồ sơ trước khi đến tay nhà tuyển dụng. Một CV đẹp mắt nhưng máy không đọc được vẫn có thể bị loại ngay từ vòng đầu. Dưới đây là những nguyên tắc giúp CV của bạn "thân thiện" với ATS.</p>

<h2>1. Chọn định dạng file đơn giản</h2>
<p>Ưu tiên file <strong>PDF xuất trực tiếp từ Word/Google Docs</strong> hoặc file <strong>.docx</strong>. Tránh PDF dạng ảnh scan vì hệ thống không trích xuất được chữ.</p>

<h2>2. Bố cục một cột, tiêu đề rõ ràng</h2>
<p>Bảng biểu, text box, cột đôi hay biểu đồ kỹ năng dạng thanh thường khiến ATS đọc sai thứ tự nội dung. Hãy dùng các tiêu đề quen thuộc như:</p>
<ul>
    <li>Thông tin liên hệ</li>
    <li>Mục tiêu nghề nghiệp</li>
    <li>Kinh nghiệm làm việc</li>
    <li>Học vấn</li>
    <li>Kỹ năng</li>
</ul>

<h2>3. Tối ưu từ khóa theo mô tả công việc</h2>
<p>Đọc kỹ JD và đưa các kỹ năng, công cụ, chứng chỉ được nhắc đến vào CV một cách tự nhiên. Ví dụ JD yêu cầu "ReactJS, TypeScript, RESTful API" thì hãy ghi đúng các thuật ngữ này thay vì viết chung chung "lập trình web".</p>

<h2>4. Định lượng thành tích</h2>
<p>Thay vì "Phụ trách tối ưu hệ thống", hãy viết "Tối ưu truy vấn giúp giảm 40% thời gian phản hồi API". Con số giúp cả hệ thống chấm điểm lẫn nhà tuyển dụng đánh giá năng lực của bạn chính xác hơn.</p>

<h2>5. Kiểm tra lần cuối</h2>
<p>Trước khi nộp, hãy thử copy toàn bộ nội dung CV sang một file text thuần. Nếu nội dung vẫn đúng thứ tự và đầy đủ, khả năng cao ATS cũng sẽ đọc được CV của bạn.</p>
""",
    },
    {
        "title": "7 câu hỏi phỏng vấn phổ biến và cách trả lời ghi điểm",
        "category": "interview",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Dù ở vị trí nào, có những câu hỏi gần như luôn xuất hiện trong buổi phỏng vấn. Chuẩn bị trước câu trả lời giúp bạn tự tin và để lại ấn tượng chuyên nghiệp.</p>

<h2>1. "Hãy giới thiệu về bản thân"</h2>
<p>Đừng kể lại toàn bộ CV. Hãy dùng công thức <strong>Hiện tại – Quá khứ – Tương lai</strong>: bạn đang làm gì, kinh nghiệm nổi bật nào dẫn bạn đến đây, và vì sao vị trí này phù hợp với định hướng của bạn. Giữ trong khoảng 1–2 phút.</p>

<h2>2. "Điểm mạnh và điểm yếu của bạn là gì?"</h2>
<p>Với điểm mạnh, chọn kỹ năng liên quan trực tiếp đến công việc và kèm ví dụ cụ thể. Với điểm yếu, hãy chọn một điểm có thật, không ảnh hưởng nghiêm trọng đến vị trí, và nói rõ bạn đang cải thiện nó như thế nào.</p>

<h2>3. "Vì sao bạn muốn làm việc tại công ty chúng tôi?"</h2>
<p>Tìm hiểu trước về sản phẩm, văn hóa và các dự án gần đây của công ty. Câu trả lời nên kết nối giữa điều công ty đang làm và mục tiêu phát triển của bạn.</p>

<h2>4. "Kể về một tình huống khó khăn bạn từng gặp"</h2>
<p>Áp dụng phương pháp <strong>STAR</strong>:</p>
<ul>
    <li><strong>S</strong>ituation – Bối cảnh</li>
    <li><strong>T</strong>ask – Nhiệm vụ của bạn</li>
    <li><strong>A</strong>ction – Hành động bạn đã thực hiện</li>
    <li><strong>R</strong>esult – Kết quả đạt được</li>
</ul>

<h2>5. "Bạn thấy mình ở đâu sau 5 năm nữa?"</h2>
<p>Nhà tuyển dụng muốn biết bạn có định hướng rõ ràng và có gắn bó lâu dài không. Hãy nói về năng lực bạn muốn đạt được thay vì một chức danh cụ thể.</p>

<h2>6. "Mức lương mong muốn của bạn là bao nhiêu?"</h2>
<p>Tham khảo mặt bằng lương thị trường trước buổi phỏng vấn và đưa ra một khoảng hợp lý, kèm lý do dựa trên kinh nghiệm và kỹ năng của bạn.</p>

<h2>7. "Bạn có câu hỏi nào cho chúng tôi không?"</h2>
<p>Đừng bao giờ trả lời "Không". Hãy hỏi về lộ trình phát triển, cách đánh giá hiệu quả công việc hoặc thử thách lớn nhất của team trong thời gian tới — điều này cho thấy bạn thực sự quan tâm đến vị trí.</p>
""",
    },
    {
        "title": "Nhảy việc hay ở lại? Cách ra quyết định nghề nghiệp đúng đắn",
        "category": "career_path",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Sau 1–3 năm đi làm, nhiều người bắt đầu băn khoăn: nên tiếp tục gắn bó để tích lũy hay chuyển việc để bứt phá? Không có câu trả lời chung cho tất cả, nhưng có những câu hỏi giúp bạn đưa ra lựa chọn sáng suốt hơn.</p>

<h2>1. Bạn còn đang học được điều gì mới không?</h2>
<p>Nếu công việc hằng ngày đã lặp lại và bạn không còn được giao thử thách mới trong 6 tháng gần đây, đó là dấu hiệu bạn đang chững lại. Hãy thử đề xuất nhận thêm trách nhiệm trước khi nghĩ đến việc rời đi.</p>

<h2>2. Lộ trình thăng tiến có rõ ràng không?</h2>
<p>Trao đổi thẳng thắn với quản lý về các mốc phát triển và tiêu chí đánh giá. Một công ty có lộ trình minh bạch thường đáng để bạn ở lại lâu hơn.</p>

<h2>3. Thu nhập đã tương xứng với năng lực chưa?</h2>
<p>Tham khảo mặt bằng lương thị trường cho vị trí và số năm kinh nghiệm của bạn. Nếu chênh lệch quá lớn và công ty không có kế hoạch điều chỉnh, việc tìm cơ hội mới là hoàn toàn hợp lý.</p>

<h2>4. Đừng nhảy việc chỉ vì cảm xúc</h2>
<p>Một tuần căng thẳng hay mâu thuẫn nhỏ với đồng nghiệp không nên là lý do duy nhất để nghỉ việc. Hãy ghi lại lý do muốn rời đi và xem chúng có còn đúng sau 1–2 tháng hay không.</p>

<h2>5. Chuẩn bị kỹ trước khi rời đi</h2>
<ul>
    <li>Cập nhật CV với những thành tích có số liệu cụ thể</li>
    <li>Có sẵn khoản dự phòng tối thiểu 3 tháng chi tiêu</li>
    <li>Bàn giao công việc chu đáo và giữ mối quan hệ tốt với công ty cũ</li>
</ul>
<p>Dù chọn ở lại hay ra đi, điều quan trọng là quyết định đó giúp bạn tiến gần hơn đến mục tiêu nghề nghiệp dài hạn.</p>
""",
    },
    {
        "title": "Ứng dụng AI trong tuyển dụng: HR cần chuẩn bị gì?",
        "category": "hr_corner",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>AI đang thay đổi cách doanh nghiệp tìm kiếm và đánh giá ứng viên. Từ sàng lọc CV tự động đến chấm điểm mức độ phù hợp, các công cụ này giúp HR tiết kiệm đáng kể thời gian — nhưng cũng đặt ra những yêu cầu mới.</p>

<h2>1. AI giúp được gì cho HR?</h2>
<ul>
    <li><strong>Sàng lọc hồ sơ nhanh:</strong> xử lý hàng trăm CV trong vài phút thay vì vài ngày.</li>
    <li><strong>Chấm điểm mức độ phù hợp:</strong> so khớp kỹ năng, kinh nghiệm của ứng viên với yêu cầu trong JD.</li>
    <li><strong>Giảm việc thủ công:</strong> tự động sắp lịch phỏng vấn, gửi email cập nhật trạng thái.</li>
</ul>

<h2>2. Viết JD rõ ràng là điều kiện tiên quyết</h2>
<p>Hệ thống AI chỉ đánh giá tốt khi mô tả công việc đủ cụ thể. Hãy liệt kê rõ kỹ năng bắt buộc, kỹ năng ưu tiên, số năm kinh nghiệm và lĩnh vực ngành nghề thay vì những yêu cầu chung chung như "năng động, chịu khó".</p>

<h2>3. Đừng để AI quyết định thay bạn</h2>
<p>Điểm số từ AI nên được xem là gợi ý để ưu tiên hồ sơ, không phải kết luận cuối cùng. Những yếu tố như thái độ, khả năng học hỏi hay sự phù hợp văn hóa vẫn cần được đánh giá qua phỏng vấn trực tiếp.</p>

<h2>4. Chú ý tính công bằng</h2>
<p>Định kỳ rà soát kết quả sàng lọc để phát hiện các xu hướng bất thường, ví dụ một nhóm ứng viên liên tục bị đánh giá thấp. Điều chỉnh trọng số tiêu chí khi cần để đảm bảo quy trình tuyển dụng minh bạch.</p>

<h2>5. Nâng cấp kỹ năng cho đội ngũ HR</h2>
<p>HR hiện đại cần hiểu cách công cụ hoạt động, biết đọc và phân tích dữ liệu tuyển dụng. Khi kết hợp tốt giữa công nghệ và đánh giá con người, doanh nghiệp sẽ tuyển đúng người nhanh hơn và hiệu quả hơn.</p>
""",
    },
    {
        "title": "5 lỗi sai phổ biến khiến CV của bạn bị loại ngay từ vòng đầu",
        "category": "cv_writing",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Nhà tuyển dụng thường chỉ dành vài chục giây cho mỗi CV. Chỉ một lỗi nhỏ cũng đủ khiến hồ sơ của bạn bị bỏ qua. Dưới đây là 5 lỗi thường gặp nhất và cách khắc phục.</p>

<h2>1. Sai chính tả và ngữ pháp</h2>
<p>Lỗi chính tả khiến bạn trông thiếu cẩn thận. Hãy đọc lại CV ít nhất hai lần, dùng công cụ kiểm tra chính tả và nhờ một người khác đọc giúp.</p>

<h2>2. Email và ảnh đại diện thiếu chuyên nghiệp</h2>
<p>Tránh các email kiểu "cobengoxinh99@...". Hãy dùng email theo họ tên. Ảnh đại diện nên rõ mặt, phông nền đơn giản, trang phục lịch sự.</p>

<h2>3. Liệt kê nhiệm vụ thay vì thành tích</h2>
<p>"Phụ trách bán hàng" không nói lên nhiều điều. Hãy viết "Tăng 25% doanh số khu vực trong 6 tháng" để nhà tuyển dụng thấy rõ giá trị bạn mang lại.</p>

<h2>4. Một CV dùng cho mọi vị trí</h2>
<p>Mỗi công việc có yêu cầu khác nhau. Hãy điều chỉnh phần mục tiêu, kỹ năng và kinh nghiệm nổi bật cho phù hợp với từng JD.</p>

<h2>5. CV quá dài hoặc quá sơ sài</h2>
<p>Với người dưới 5 năm kinh nghiệm, CV nên gói gọn trong 1–2 trang. Chỉ giữ lại những thông tin liên quan đến vị trí ứng tuyển.</p>
""",
    },
    {
        "title": "Cách trả lời câu hỏi về mức lương mong muốn khi phỏng vấn",
        "category": "interview",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>"Mức lương mong muốn của bạn là bao nhiêu?" là câu hỏi khiến nhiều ứng viên lúng túng nhất. Trả lời quá thấp thì thiệt thòi, quá cao thì dễ mất cơ hội. Dưới đây là cách chuẩn bị để bạn tự tin thương lượng.</p>

<h2>1. Nghiên cứu mặt bằng lương trước</h2>
<p>Tham khảo các báo cáo lương, tin tuyển dụng cùng vị trí và hỏi ý kiến người quen trong ngành. Xác định mức lương thị trường phù hợp với kinh nghiệm và khu vực làm việc của bạn.</p>

<h2>2. Đưa ra một khoảng thay vì một con số</h2>
<p>Ví dụ: "Với kinh nghiệm 3 năm và các dự án tôi đã tham gia, tôi mong muốn mức lương trong khoảng 18–22 triệu". Hãy đặt mức tối thiểu bạn chấp nhận được ở gần đầu dưới của khoảng.</p>

<h2>3. Giải thích dựa trên giá trị bạn mang lại</h2>
<p>Đừng nói lý do cá nhân như chi phí sinh hoạt. Hãy dựa vào kỹ năng, thành tích và mức độ đóng góp bạn có thể tạo ra cho công ty.</p>

<h2>4. Cân nhắc toàn bộ gói đãi ngộ</h2>
<p>Ngoài lương cứng, hãy hỏi thêm về thưởng, bảo hiểm, ngày phép, chế độ làm việc từ xa và cơ hội đào tạo. Đôi khi một gói phúc lợi tốt bù đắp được phần lương thấp hơn mong đợi.</p>

<h2>5. Giữ thái độ cởi mở</h2>
<p>Thương lượng là cuộc trao đổi hai chiều. Hãy lịch sự, tự tin và sẵn sàng lắng nghe đề xuất từ phía công ty.</p>
""",
    },
    {
        "title": "Lộ trình phát triển sự nghiệp cho sinh viên mới ra trường",
        "category": "career_path",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Những năm đầu sau khi tốt nghiệp là giai đoạn đặt nền móng cho cả sự nghiệp. Một lộ trình rõ ràng sẽ giúp bạn tránh lãng phí thời gian và phát triển nhanh hơn.</p>

<h2>Năm thứ nhất: Học cách làm việc chuyên nghiệp</h2>
<p>Tập trung vào việc hiểu quy trình, rèn kỹ năng giao tiếp, quản lý thời gian và tinh thần trách nhiệm. Đừng ngại hỏi và ghi chép lại những gì học được mỗi ngày.</p>

<h2>Năm thứ hai: Xây dựng chuyên môn cốt lõi</h2>
<p>Chọn một mảng chuyên môn bạn yêu thích và đào sâu. Tham gia các khóa học, lấy chứng chỉ liên quan và chủ động nhận những nhiệm vụ khó hơn.</p>

<h2>Năm thứ ba: Tạo dấu ấn cá nhân</h2>
<p>Bắt đầu dẫn dắt các đầu việc nhỏ, chia sẻ kiến thức với đồng nghiệp mới và xây dựng mạng lưới quan hệ trong ngành. Đây là lúc bạn nên đánh giá lại định hướng dài hạn.</p>

<h2>Một vài lời khuyên</h2>
<ul>
    <li>Ưu tiên môi trường giúp bạn học hỏi hơn là mức lương cao ở giai đoạn đầu.</li>
    <li>Tìm một người hướng dẫn (mentor) có kinh nghiệm trong lĩnh vực bạn theo đuổi.</li>
    <li>Cập nhật CV và hồ sơ trực tuyến mỗi 6 tháng.</li>
</ul>
""",
    },
    {
        "title": "Xây dựng thương hiệu nhà tuyển dụng để thu hút nhân tài",
        "category": "hr_corner",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Ứng viên giỏi ngày nay không chỉ chọn công việc mà còn chọn nơi làm việc. Thương hiệu nhà tuyển dụng (Employer Branding) mạnh giúp doanh nghiệp thu hút đúng người với chi phí thấp hơn.</p>

<h2>1. Xác định giá trị cốt lõi của doanh nghiệp</h2>
<p>Điều gì khiến công ty bạn khác biệt? Đó có thể là văn hóa cởi mở, cơ hội thăng tiến nhanh hay sản phẩm có tác động xã hội. Hãy truyền tải những điểm này một cách nhất quán.</p>

<h2>2. Để nhân viên trở thành người kể chuyện</h2>
<p>Những chia sẻ thật từ nhân viên đáng tin hơn bất kỳ quảng cáo nào. Khuyến khích họ chia sẻ trải nghiệm làm việc trên mạng xã hội và trang tuyển dụng của công ty.</p>

<h2>3. Tối ưu trải nghiệm ứng viên</h2>
<p>Phản hồi nhanh, quy trình rõ ràng và thông báo kết quả cho cả những ứng viên không trúng tuyển. Một trải nghiệm tốt khiến ứng viên sẵn sàng quay lại hoặc giới thiệu người khác.</p>

<h2>4. Hoàn thiện trang hồ sơ công ty</h2>
<p>Cập nhật đầy đủ thông tin, hình ảnh văn phòng, phúc lợi và các vị trí đang tuyển trên nền tảng tuyển dụng. Đây thường là nơi ứng viên tìm hiểu đầu tiên.</p>

<h2>5. Đo lường hiệu quả</h2>
<p>Theo dõi số lượng ứng viên, tỉ lệ chấp nhận offer và thời gian tuyển dụng để biết chiến lược nào đang thực sự hiệu quả.</p>
""",
    },
    {
        "title": "Viết mục tiêu nghề nghiệp trong CV sao cho thuyết phục",
        "category": "cv_writing",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Mục tiêu nghề nghiệp là phần nhà tuyển dụng thường đọc đầu tiên, nhưng cũng là phần nhiều người viết sơ sài nhất. Một mục tiêu tốt cho thấy bạn hiểu mình muốn gì và phù hợp với vị trí ứng tuyển.</p>

<h2>Những lỗi thường gặp</h2>
<ul>
    <li>Viết chung chung: "Mong muốn làm việc trong môi trường chuyên nghiệp".</li>
    <li>Chỉ nói về lợi ích bản thân mà không nhắc đến đóng góp cho công ty.</li>
    <li>Quá dài, kể lại toàn bộ kinh nghiệm.</li>
</ul>

<h2>Công thức gợi ý</h2>
<p><strong>Kinh nghiệm/Thế mạnh + Vị trí mong muốn + Giá trị đóng góp + Định hướng phát triển.</strong></p>

<h2>Ví dụ</h2>
<p><em>"Lập trình viên Frontend với 2 năm kinh nghiệm ReactJS, mong muốn đảm nhận vị trí Frontend Developer để xây dựng giao diện có hiệu năng cao, thân thiện với người dùng. Trong 2 năm tới, tôi hướng đến vai trò Senior và tham gia thiết kế kiến trúc hệ thống."</em></p>

<h2>Lưu ý</h2>
<p>Giữ phần mục tiêu trong 2–4 câu và điều chỉnh theo từng công ty. Nếu có thể, hãy dùng các từ khóa xuất hiện trong mô tả công việc.</p>
""",
    },
    {
        "title": "Phỏng vấn online: Những điều cần chuẩn bị để gây ấn tượng",
        "category": "interview",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Phỏng vấn trực tuyến đã trở thành vòng phổ biến trong quy trình tuyển dụng. Dù không gặp mặt, bạn vẫn cần chuẩn bị chu đáo không kém phỏng vấn trực tiếp.</p>

<h2>1. Kiểm tra thiết bị trước 30 phút</h2>
<p>Đảm bảo camera, micro, tai nghe và đường truyền internet ổn định. Cài sẵn và đăng nhập ứng dụng họp (Google Meet, Zoom, Teams) để tránh mất thời gian.</p>

<h2>2. Chọn không gian phù hợp</h2>
<p>Ngồi ở nơi yên tĩnh, đủ ánh sáng, phông nền gọn gàng. Ánh sáng nên chiếu từ phía trước mặt thay vì sau lưng.</p>

<h2>3. Trang phục chỉn chu</h2>
<p>Ăn mặc lịch sự như khi đến văn phòng. Điều này không chỉ tạo ấn tượng tốt mà còn giúp bạn tự tin hơn.</p>

<h2>4. Giao tiếp qua màn hình</h2>
<ul>
    <li>Nhìn vào camera khi nói để tạo cảm giác giao tiếp bằng mắt.</li>
    <li>Nói chậm, rõ ràng và chờ người phỏng vấn nói xong mới trả lời.</li>
    <li>Tắt thông báo điện thoại và máy tính.</li>
</ul>

<h2>5. Gửi email cảm ơn sau buổi phỏng vấn</h2>
<p>Một email ngắn cảm ơn và nhắc lại sự quan tâm đến vị trí giúp bạn được nhớ đến lâu hơn.</p>
""",
    },
    {
        "title": "Chuyển ngành ở tuổi 30: Bắt đầu từ đâu?",
        "category": "career_path",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Chuyển ngành ở tuổi 30 không phải là quá muộn. Nhiều người đã thành công rực rỡ sau khi đổi hướng. Điều quan trọng là bạn có kế hoạch rõ ràng và tận dụng được kinh nghiệm sẵn có.</p>

<h2>1. Hiểu rõ lý do muốn chuyển ngành</h2>
<p>Bạn chán công việc hiện tại hay thực sự đam mê lĩnh vực mới? Hãy tìm hiểu kỹ công việc thực tế của ngành mới qua người trong nghề trước khi quyết định.</p>

<h2>2. Tận dụng kỹ năng chuyển đổi</h2>
<p>Kỹ năng quản lý, giao tiếp, phân tích hay hiểu biết về một lĩnh vực cụ thể đều có giá trị. Ví dụ, một kế toán chuyển sang phân tích dữ liệu có lợi thế lớn về hiểu biết tài chính.</p>

<h2>3. Học có lộ trình</h2>
<p>Chọn các khóa học có dự án thực tế, lấy chứng chỉ được công nhận và xây dựng portfolio để chứng minh năng lực.</p>

<h2>4. Bắt đầu từ những bước nhỏ</h2>
<ul>
    <li>Nhận dự án freelance hoặc làm thêm trong lĩnh vực mới.</li>
    <li>Tìm vị trí kết hợp giữa ngành cũ và ngành mới.</li>
    <li>Chuẩn bị tài chính cho giai đoạn thu nhập có thể giảm.</li>
</ul>

<h2>5. Kiên nhẫn</h2>
<p>Thường mất 6–18 tháng để chuyển ngành thành công. Hãy đặt mục tiêu theo từng giai đoạn và theo dõi tiến độ của bản thân.</p>
""",
    },
    {
        "title": "Quy trình onboarding nhân viên mới hiệu quả trong 30 ngày đầu",
        "category": "hr_corner",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>30 ngày đầu tiên quyết định phần lớn việc nhân viên mới có gắn bó lâu dài hay không. Một quy trình onboarding bài bản giúp họ hòa nhập nhanh và làm việc hiệu quả sớm hơn.</p>

<h2>Trước ngày đầu tiên</h2>
<ul>
    <li>Gửi email chào mừng kèm lịch tuần đầu và thông tin cần thiết.</li>
    <li>Chuẩn bị sẵn máy tính, tài khoản và chỗ ngồi.</li>
    <li>Chỉ định một người đồng hành (buddy) hỗ trợ nhân viên mới.</li>
</ul>

<h2>Tuần đầu tiên: Hòa nhập</h2>
<p>Giới thiệu văn hóa, giá trị cốt lõi, cơ cấu tổ chức và đồng nghiệp. Tránh giao quá nhiều việc khiến nhân viên bị quá tải.</p>

<h2>Tuần 2–3: Làm quen công việc</h2>
<p>Giao các nhiệm vụ nhỏ có mục tiêu rõ ràng. Quản lý trực tiếp nên có buổi trao đổi 1-1 hằng tuần để giải đáp thắc mắc.</p>

<h2>Tuần 4: Đánh giá và định hướng</h2>
<p>Cùng nhân viên nhìn lại tháng đầu tiên, ghi nhận những điểm làm tốt và thống nhất mục tiêu cho giai đoạn thử việc tiếp theo.</p>

<h2>Thu thập phản hồi</h2>
<p>Hỏi nhân viên mới về trải nghiệm onboarding để liên tục cải thiện quy trình cho những người đến sau.</p>
""",
    },
    {
        "title": "CV cho người chưa có kinh nghiệm: Làm sao để nổi bật?",
        "category": "cv_writing",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Chưa có kinh nghiệm đi làm không có nghĩa là CV của bạn phải trống trải. Sinh viên và người mới ra trường vẫn có nhiều cách để thể hiện năng lực với nhà tuyển dụng.</p>

<h2>1. Đưa học vấn lên đầu</h2>
<p>Ghi rõ trường, chuyên ngành, điểm trung bình (nếu tốt) và các môn học liên quan đến vị trí ứng tuyển.</p>

<h2>2. Khai thác dự án học tập</h2>
<p>Đồ án, bài tập lớn hay dự án nhóm đều là kinh nghiệm thực tế. Hãy mô tả vai trò của bạn, công nghệ/công cụ đã dùng và kết quả đạt được.</p>

<h2>3. Hoạt động ngoại khóa và tình nguyện</h2>
<p>Vai trò trưởng ban trong câu lạc bộ hay tổ chức sự kiện cho thấy kỹ năng lãnh đạo, làm việc nhóm và quản lý thời gian.</p>

<h2>4. Việc làm thêm và thực tập</h2>
<p>Kể cả công việc bán thời gian không liên quan trực tiếp cũng thể hiện tinh thần trách nhiệm và kỹ năng giao tiếp.</p>

<h2>5. Kỹ năng và chứng chỉ</h2>
<p>Liệt kê ngoại ngữ, tin học, các khóa học online đã hoàn thành. Nếu có portfolio hoặc GitHub, hãy đính kèm đường link.</p>
""",
    },
    {
        "title": "Phương pháp STAR: Bí quyết trả lời câu hỏi hành vi",
        "category": "interview",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Các câu hỏi như "Hãy kể về lần bạn giải quyết mâu thuẫn trong nhóm" được gọi là câu hỏi hành vi. Nhà tuyển dụng dùng chúng để dự đoán cách bạn xử lý tình huống trong tương lai. Phương pháp STAR giúp câu trả lời của bạn mạch lạc và thuyết phục.</p>

<h2>STAR là gì?</h2>
<ul>
    <li><strong>Situation (Tình huống):</strong> Bối cảnh xảy ra sự việc.</li>
    <li><strong>Task (Nhiệm vụ):</strong> Trách nhiệm hoặc mục tiêu của bạn.</li>
    <li><strong>Action (Hành động):</strong> Những bước cụ thể bạn đã làm.</li>
    <li><strong>Result (Kết quả):</strong> Kết quả đạt được, tốt nhất là có số liệu.</li>
</ul>

<h2>Ví dụ</h2>
<p><em>"Dự án của nhóm tôi bị chậm 2 tuần so với kế hoạch (S). Là trưởng nhóm, tôi cần đưa dự án về đúng tiến độ (T). Tôi chia nhỏ công việc, tổ chức họp nhanh mỗi sáng và chủ động hỗ trợ phần việc đang bị nghẽn (A). Kết quả, dự án hoàn thành sớm hơn hạn chót 3 ngày và được khách hàng đánh giá cao (R)."</em></p>

<h2>Mẹo áp dụng</h2>
<p>Chuẩn bị trước 4–5 câu chuyện có thể dùng cho nhiều câu hỏi khác nhau. Tập trung nhiều nhất vào phần Hành động vì đó là nơi thể hiện năng lực của bạn.</p>
""",
    },
    {
        "title": "Kỹ năng mềm nào quan trọng nhất trong thời đại AI?",
        "category": "career_path",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Khi AI đảm nhận ngày càng nhiều công việc lặp lại, những kỹ năng chỉ con người mới có trở nên giá trị hơn bao giờ hết. Đây là những kỹ năng mềm bạn nên đầu tư ngay từ hôm nay.</p>

<h2>1. Tư duy phản biện</h2>
<p>AI có thể đưa ra câu trả lời, nhưng con người cần đánh giá xem câu trả lời đó có đúng và phù hợp hay không.</p>

<h2>2. Khả năng học hỏi liên tục</h2>
<p>Công nghệ thay đổi rất nhanh. Người biết tự học và thích nghi sẽ luôn có lợi thế trên thị trường lao động.</p>

<h2>3. Giao tiếp và thuyết phục</h2>
<p>Trình bày ý tưởng rõ ràng, lắng nghe và đàm phán là những kỹ năng mà máy móc khó thay thế.</p>

<h2>4. Trí tuệ cảm xúc</h2>
<p>Hiểu và quản lý cảm xúc của bản thân, đồng cảm với người khác giúp bạn làm việc nhóm và lãnh đạo hiệu quả hơn.</p>

<h2>5. Sáng tạo và giải quyết vấn đề</h2>
<p>Kết hợp kiến thức từ nhiều lĩnh vực để tạo ra giải pháp mới là thế mạnh đặc biệt của con người.</p>

<p>Hãy xem AI như một công cụ hỗ trợ. Người biết tận dụng AI cùng với kỹ năng mềm vững vàng sẽ là người dẫn đầu.</p>
""",
    },
    {
        "title": "Giữ chân nhân tài: 5 chiến lược giảm tỉ lệ nghỉ việc",
        "category": "hr_corner",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Chi phí thay thế một nhân viên có thể lên tới vài tháng lương của vị trí đó. Vì vậy, giữ chân nhân tài quan trọng không kém việc tuyển dụng.</p>

<h2>1. Lộ trình phát triển rõ ràng</h2>
<p>Nhân viên muốn biết họ sẽ đi đến đâu nếu gắn bó. Xây dựng khung năng lực và tiêu chí thăng tiến minh bạch cho từng vị trí.</p>

<h2>2. Chế độ đãi ngộ cạnh tranh</h2>
<p>Định kỳ so sánh mức lương với thị trường và điều chỉnh kịp thời, tránh để nhân viên phải nghỉ việc mới được tăng lương.</p>

<h2>3. Ghi nhận đúng lúc</h2>
<p>Một lời khen công khai hay phần thưởng nhỏ sau khi hoàn thành dự án có tác động lớn đến động lực làm việc.</p>

<h2>4. Quản lý trực tiếp là yếu tố then chốt</h2>
<p>Nhiều người nghỉ việc vì quản lý chứ không vì công ty. Đào tạo kỹ năng lãnh đạo cho đội ngũ quản lý là khoản đầu tư xứng đáng.</p>

<h2>5. Lắng nghe nhân viên</h2>
<p>Tổ chức khảo sát mức độ hài lòng, các buổi trao đổi 1-1 và phỏng vấn nghỉ việc để hiểu nguyên nhân thật sự và cải thiện kịp thời.</p>
""",
    },
    {
        "title": "Cách trình bày kỹ năng trong CV để thuyết phục nhà tuyển dụng",
        "category": "cv_writing",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Phần kỹ năng giúp nhà tuyển dụng và hệ thống ATS nhanh chóng đánh giá bạn có phù hợp với vị trí hay không. Tuy nhiên, nhiều CV chỉ liệt kê kỹ năng một cách hời hợt.</p>

<h2>1. Tách kỹ năng chuyên môn và kỹ năng mềm</h2>
<p>Kỹ năng chuyên môn như "Python, SQL, Excel nâng cao" nên được đặt lên trước. Kỹ năng mềm như "giao tiếp, làm việc nhóm" nên đi kèm ví dụ trong phần kinh nghiệm.</p>

<h2>2. Ưu tiên kỹ năng có trong JD</h2>
<p>Sắp xếp những kỹ năng được yêu cầu trong mô tả công việc lên đầu và dùng đúng thuật ngữ mà nhà tuyển dụng sử dụng.</p>

<h2>3. Thể hiện mức độ thành thạo</h2>
<p>Thay vì các thanh phần trăm khó hiểu, hãy ghi rõ: "Tiếng Anh – IELTS 7.0" hoặc "ReactJS – 2 năm, 5 dự án thực tế".</p>

<h2>4. Chứng minh bằng kinh nghiệm</h2>
<p>Mỗi kỹ năng quan trọng nên xuất hiện lại trong phần kinh nghiệm hoặc dự án, kèm kết quả cụ thể.</p>

<h2>5. Đừng liệt kê quá nhiều</h2>
<p>Khoảng 8–12 kỹ năng liên quan là đủ. Một danh sách quá dài khiến nhà tuyển dụng nghi ngờ về độ sâu chuyên môn của bạn.</p>
""",
    },
    {
        "title": "Những câu hỏi nên hỏi lại nhà tuyển dụng cuối buổi phỏng vấn",
        "category": "interview",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Khi nhà tuyển dụng hỏi "Bạn có câu hỏi nào không?", đây là cơ hội để bạn thể hiện sự quan tâm và tìm hiểu xem công việc có thực sự phù hợp với mình.</p>

<h2>Về công việc</h2>
<ul>
    <li>Một ngày làm việc điển hình ở vị trí này diễn ra như thế nào?</li>
    <li>Kết quả nào được kỳ vọng trong 3 tháng đầu tiên?</li>
</ul>

<h2>Về đội nhóm</h2>
<ul>
    <li>Team hiện có bao nhiêu người và phối hợp với những bộ phận nào?</li>
    <li>Thử thách lớn nhất của team trong thời gian tới là gì?</li>
</ul>

<h2>Về phát triển</h2>
<ul>
    <li>Công ty đánh giá hiệu quả công việc như thế nào?</li>
    <li>Nhân viên có cơ hội đào tạo và thăng tiến ra sao?</li>
</ul>

<h2>Về quy trình</h2>
<ul>
    <li>Các bước tiếp theo của quy trình tuyển dụng là gì?</li>
</ul>

<h2>Những câu nên tránh</h2>
<p>Đừng hỏi những thông tin đã có sẵn trên website hoặc JD. Cũng không nên hỏi ngay về ngày nghỉ hay lương thưởng ở vòng đầu tiên, trừ khi nhà tuyển dụng chủ động nhắc đến.</p>
""",
    },
    {
        "title": "Làm sao để xin tăng lương thành công?",
        "category": "career_path",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Nhiều người ngại đề xuất tăng lương vì sợ bị từ chối hoặc làm mất lòng cấp trên. Thực tế, nếu chuẩn bị kỹ, đây là cuộc trao đổi hoàn toàn bình thường và chuyên nghiệp.</p>

<h2>1. Chọn thời điểm phù hợp</h2>
<p>Thời điểm tốt nhất là sau khi bạn hoàn thành xuất sắc một dự án, trong kỳ đánh giá hiệu suất hoặc khi công ty đang làm ăn tốt.</p>

<h2>2. Chuẩn bị bằng chứng</h2>
<p>Liệt kê những thành tích cụ thể: dự án đã hoàn thành, doanh thu mang về, chi phí tiết kiệm được hay trách nhiệm mới bạn đã đảm nhận.</p>

<h2>3. Tìm hiểu mặt bằng thị trường</h2>
<p>Biết mức lương của vị trí tương đương ở công ty khác giúp bạn đưa ra đề xuất hợp lý và có cơ sở.</p>

<h2>4. Trình bày tích cực</h2>
<p>Tập trung vào giá trị bạn mang lại và mong muốn tiếp tục đóng góp, thay vì so sánh với đồng nghiệp hay đe dọa nghỉ việc.</p>

<h2>5. Nếu bị từ chối</h2>
<p>Hỏi rõ bạn cần đạt được điều gì để được xem xét trong lần tới và thống nhất mốc thời gian cụ thể.</p>
""",
    },
    {
        "title": "Xây dựng bộ câu hỏi phỏng vấn theo năng lực cho HR",
        "category": "hr_corner",
        "thumbnail_url": "",
        "author_name": "Ban Biên Tập",
        "content_html": """
<p>Phỏng vấn theo cảm tính dễ dẫn đến tuyển sai người. Phỏng vấn theo năng lực (Competency-based Interview) giúp HR đánh giá ứng viên khách quan và nhất quán hơn.</p>

<h2>1. Xác định năng lực cần có</h2>
<p>Làm việc với quản lý bộ phận để liệt kê 4–6 năng lực quan trọng nhất cho vị trí, ví dụ: giải quyết vấn đề, làm việc nhóm, chịu áp lực.</p>

<h2>2. Viết câu hỏi hành vi cho từng năng lực</h2>
<p>Ví dụ với năng lực giải quyết vấn đề: <em>"Hãy kể về một lần bạn gặp sự cố nghiêm trọng trong công việc. Bạn đã xử lý như thế nào?"</em></p>

<h2>3. Xây dựng thang điểm đánh giá</h2>
<p>Mô tả rõ thế nào là câu trả lời đạt 1, 3 hay 5 điểm. Điều này giúp nhiều người phỏng vấn cùng đánh giá theo một chuẩn chung.</p>

<h2>4. Dùng câu hỏi đào sâu</h2>
<p>"Cụ thể bạn đã làm gì?", "Kết quả ra sao?", "Nếu làm lại, bạn sẽ thay đổi điều gì?" giúp phân biệt ứng viên có kinh nghiệm thật với câu trả lời học thuộc.</p>

<h2>5. Kết hợp với dữ liệu sàng lọc</h2>
<p>Đối chiếu kết quả phỏng vấn với điểm đánh giá CV từ hệ thống để có cái nhìn toàn diện trước khi đưa ra quyết định cuối cùng.</p>
""",
    },
]


async def seed_blogs():
    await connect_to_mongo()

    inserted = 0
    now = datetime.now(timezone.utc)
    for index, post in enumerate(BLOG_POSTS):
        slug = AdminService._generate_slug(post["title"])
        if await BlogRepository.find_one({"slug": slug}):
            print(f"Bỏ qua (đã tồn tại): {slug}")
            continue

        created_at = now - timedelta(days=index)
        await BlogRepository.create({
            **post,
            "content_html": post["content_html"].strip(),
            "is_published": True,
            "slug": slug,
            "reading_time_minutes": AdminService._calculate_reading_time(post["content_html"]),
            "view_count": 0,
            "created_by_admin_id": None,
            "created_at": created_at,
            "updated_at": created_at,
        })
        inserted += 1
        print(f"Đã thêm bài viết: {slug}")

    print(f"Hoàn tất! Đã thêm {inserted} bài viết.")
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(seed_blogs())
