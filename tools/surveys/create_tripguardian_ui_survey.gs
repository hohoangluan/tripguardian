function createTripGuardianSurvey() {
  const form = FormApp.create('Khảo sát UI/UX TripGuardian');

  form.setDescription(
    'Xin chào bạn! Chúng mình là nhóm Mây Trắng Qua Đồi, thực hiện dự án TripGuardian.\n\n' +
    'TripGuardian hỗ trợ tìm địa điểm và lập lịch trình du lịch Đà Lạt. ' +
    'Khảo sát ngắn này nhằm ghi nhận cảm nhận về giao diện và mức độ dễ sử dụng của website.\n\n' +
    'HƯỚNG DẪN\n' +
    '1. Trải nghiệm trên máy tính tại https://tripguardianfinal.visioncare-host.uk/\n' +
    '2. Thử các bước Tìm hiểu → Lựa chọn → Lịch trình trong khả năng của bạn.\n' +
    '3. Chỉ đánh giá những gì đã trực tiếp trải nghiệm; bỏ qua dòng chưa đủ cơ sở nhận xét.\n\n' +
    'Thời gian trả lời dự kiến: 2–3 phút, chưa tính thời gian dùng thử. ' +
    'Tham gia hoàn toàn tự nguyện; bạn có thể dừng bất kỳ lúc nào. ' +
    'Biểu mẫu không yêu cầu họ tên hoặc email. Phản hồi dùng để cải thiện dự án.\n\n' +
    'Liên hệ: TripGuardian1010@gmail.com'
  );
  form.setConfirmationMessage('Cảm ơn bạn đã phản hồi! Góp ý của bạn giúp nhóm cải thiện giao diện và trải nghiệm TripGuardian.');
  form.setCollectEmail(false);
  form.setLimitOneResponsePerUser(false);
  form.setProgressBar(true);
  form.setShuffleQuestions(false);
  form.setPublishingSummary(false);
  form.setAcceptingResponses(true);

  const columns = [
    '1 — Hoàn toàn không đồng ý',
    '2 — Không đồng ý',
    '3 — Trung lập',
    '4 — Đồng ý',
    '5 — Hoàn toàn đồng ý'
  ];

  function addGrid(title, rows, helpText) {
    return form.addGridItem()
      .setTitle(title)
      .setHelpText(helpText)
      .setRows(rows)
      .setColumns(columns)
      .setRequired(false);
  }

  const consent = form.addMultipleChoiceItem()
    .setTitle('Bạn có đồng ý tham gia khảo sát sau khi đọc thông tin trên không?')
    .setRequired(true);

  const contextPage = form.addPageBreakItem()
    .setTitle('Phần A — Trải nghiệm của bạn');

  form.addMultipleChoiceItem()
    .setTitle('A1. Bạn dùng thiết bị nào trong lần trải nghiệm này?')
    .setChoiceValues(['Máy tính để bàn hoặc laptop', 'Điện thoại', 'Máy tính bảng', 'Khác', 'Chưa trải nghiệm'])
    .setRequired(true);

  // Keep the routing question last on its page.
  const experience = form.addMultipleChoiceItem()
    .setTitle('A2. Bạn đã trải nghiệm TripGuardian đến đâu?')
    .setHelpText('Chọn mức xa nhất bạn đã trực tiếp sử dụng hoặc xem được.')
    .setRequired(true);

  const ratingPage = form.addPageBreakItem()
    .setTitle('Phần B — Đánh giá giao diện và trải nghiệm')
    .setHelpText(
      'Mỗi dòng chọn một mức từ 1 đến 5.\n' +
      columns.join('\n') + '\n\n' +
      'Bỏ trống dòng chưa trải nghiệm hoặc chưa đủ cơ sở đánh giá. ' +
      'Mức 3 là trung lập, không có nghĩa là chưa sử dụng.'
    );

  addGrid('B1. Hình thức giao diện', [
    'Bố cục các phần trên màn hình dễ theo dõi.',
    'Chữ trên giao diện dễ đọc.',
    'Màu sắc của giao diện dễ nhìn.'
  ], 'Đánh giá các màn hình bạn đã xem.');

  addGrid('B2. Tính dễ sử dụng', [
    'Tôi dễ nhận ra cách bắt đầu tạo một chuyến đi.',
    'Nhãn trên các nút giúp tôi hiểu thao tác sẽ thực hiện.',
    'Tôi dễ chuyển giữa các bước của chuyến đi.'
  ], 'Chỉ đánh giá những thao tác bạn đã thử.');

  addGrid('B3. Các màn hình chính và cảm nhận chung', [
    'Tôi dễ nhập nhu cầu trong màn Tìm hiểu.',
    'Tôi dễ chọn hoặc bỏ chọn địa điểm trong màn Lựa chọn.',
    'Tôi dễ theo dõi các điểm đến theo từng ngày trong màn Lịch trình.',
    'Nhìn chung, tôi hài lòng với giao diện TripGuardian.'
  ], 'Chưa dùng màn nào thì bỏ qua dòng tương ứng; dòng cuối đánh giá cảm nhận chung.');

  const feedbackPage = form.addPageBreakItem()
    .setTitle('Phần C — Góp ý')
    .setHelpText('Nếu chưa sử dụng được, bạn có thể mô tả điều đã cản trở mình.');

  form.addParagraphTextItem()
    .setTitle('C1. Bạn muốn cải thiện điều gì nhất ở giao diện hoặc cách thao tác của TripGuardian?')
    .setHelpText('Có thể nêu màn hình, thao tác khó hiểu hoặc lỗi bạn gặp. Không cung cấp thông tin cá nhân nhạy cảm.')
    .setRequired(false);

  consent.setChoices([
    consent.createChoice('Đồng ý tham gia', contextPage),
    consent.createChoice('Không đồng ý tham gia', FormApp.PageNavigationType.SUBMIT)
  ]);

  experience.setChoices([
    experience.createChoice('Chỉ xem trang giới thiệu hoặc màn đăng nhập', ratingPage),
    experience.createChoice('Đã vào trang Dành cho bạn', ratingPage),
    experience.createChoice('Đã thử bước Tìm hiểu', ratingPage),
    experience.createChoice('Đã thử bước Lựa chọn địa điểm', ratingPage),
    experience.createChoice('Đã xem hoặc chỉnh sửa Lịch trình', ratingPage),
    experience.createChoice('Chỉ thấy trang giới thiệu ứng dụng trên điện thoại', feedbackPage),
    experience.createChoice('Đã thử truy cập nhưng không xem được giao diện', feedbackPage),
    experience.createChoice('Chưa truy cập website', feedbackPage)
  ]);

  Logger.log('FORM ID: ' + form.getId());
  Logger.log('FORM EDIT URL: ' + form.getEditUrl());
  Logger.log('FORM RESPOND URL: ' + form.getPublishedUrl());
  return form.getId();
}
